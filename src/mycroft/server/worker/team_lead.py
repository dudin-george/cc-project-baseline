"""Team Lead — Claude Agent SDK persistent session per service.

Each Team Lead coordinates sub-agents for a single service:
CodeWriter → UnitTester → QATester → PR for each task.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mycroft.server.settings import settings
from mycroft.server.worker.blocker import PendingBlocker, cleanup_blocker, create_blocker
from mycroft.server.worker.sub_agents import (
    SubAgentResult,
    run_code_writer,
    run_qa_tester,
    run_unit_tester,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    task_id: str
    task_title: str
    success: bool
    code_writer: SubAgentResult | None = None
    unit_tester: SubAgentResult | None = None
    qa_tester: SubAgentResult | None = None
    pr_url: str = ""
    error: str = ""


@dataclass
class TeamLeadState:
    service_name: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    completed: list[TaskResult] = field(default_factory=list)
    current_task: str = ""
    paused: bool = False
    cancelled: bool = False


class TeamLead:
    """Manages execution of all tasks for a single service."""

    def __init__(
        self,
        project_id: str,
        service_name: str,
        repo_path: Path,
        claude_md: str,
        business_spec: str,
        tasks: list[dict[str, Any]],
    ) -> None:
        self.project_id = project_id
        self.service_name = service_name
        self.repo_path = repo_path
        self.claude_md = claude_md
        self.business_spec = business_spec
        self.state = TeamLeadState(service_name=service_name, tasks=list(tasks))
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially

    @property
    def is_paused(self) -> bool:
        return self.state.paused

    def pause(self) -> None:
        self.state.paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        self.state.paused = False
        self._pause_event.set()

    def cancel(self) -> None:
        self.state.cancelled = True
        self._pause_event.set()  # unblock if paused

    async def run(self) -> list[TaskResult]:
        """Process all tasks in order. Returns results for each task."""
        results: list[TaskResult] = []

        for task in self.state.tasks:
            if self.state.cancelled:
                break

            # Wait if paused
            await self._pause_event.wait()
            if self.state.cancelled:
                break

            task_id = task.get("id", "unknown")
            task_title = task.get("title", "Untitled")
            self.state.current_task = task_title

            logger.info(
                "[%s] Starting task: %s (%s)",
                self.service_name,
                task_title,
                task_id,
            )

            result = await self._execute_task(task)
            results.append(result)
            self.state.completed.append(result)

            if not result.success:
                # Retry once
                retry = settings.worker_retry_count
                for attempt in range(retry):
                    logger.info(
                        "[%s] Retrying task %s (attempt %d/%d)",
                        self.service_name,
                        task_title,
                        attempt + 1,
                        retry,
                    )
                    result = await self._execute_task(task)
                    if result.success:
                        # Replace the failed result
                        self.state.completed[-1] = result
                        results[-1] = result
                        break

        self.state.current_task = ""
        return results

    async def _execute_task(self, task: dict[str, Any]) -> TaskResult:
        """Execute the full pipeline for a single task: code → test → QA."""
        task_id = task.get("id", "unknown")
        task_title = task.get("title", "Untitled")
        task_desc = task.get("description", "")

        # Build task prompt from task data
        task_prompt = f"## Task: {task_title}\n\n{task_desc}"

        # 1. CodeWriter
        code_result = await run_code_writer(
            self.repo_path, task_prompt, self.claude_md
        )
        if not code_result.success:
            return TaskResult(
                task_id=task_id,
                task_title=task_title,
                success=False,
                code_writer=code_result,
                error=f"CodeWriter failed: {code_result.error}",
            )

        # 2. UnitTester
        test_prompt = (
            f"## Task: {task_title}\n\n"
            f"Write unit tests for the implementation.\n\n{task_desc}"
        )
        test_result = await run_unit_tester(
            self.repo_path, test_prompt, self.claude_md
        )
        if not test_result.success:
            return TaskResult(
                task_id=task_id,
                task_title=task_title,
                success=False,
                code_writer=code_result,
                unit_tester=test_result,
                error=f"UnitTester failed: {test_result.error}",
            )

        # 3. QATester
        qa_result = await run_qa_tester(
            self.repo_path,
            self.business_spec,
            task.get("test_commands", ["pytest tests/ -v"]),
        )

        success = qa_result.success
        return TaskResult(
            task_id=task_id,
            task_title=task_title,
            success=success,
            code_writer=code_result,
            unit_tester=test_result,
            qa_tester=qa_result,
            error="" if success else f"QATester failed: {qa_result.error}",
        )
