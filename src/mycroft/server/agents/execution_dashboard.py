"""Step 5: Execution Dashboard Agent — manages Team Leads and worker orchestration.

Unlike other agents, this one does NOT follow the standard conversation loop.
It interprets commands (start, pause, resume, status) and manages the Orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from mycroft.shared.protocol import ErrorMessage, StepId, WorkerBatchUpdate
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import user_confirm
from mycroft.server.linear.client import LinearClient
from mycroft.server.settings import settings as server_settings
from mycroft.server.worker.execution_state import (
    ExecutionState,
    ServiceRecord,
    TaskRecord,
    recover_execution,
)
from mycroft.server.worker.orchestrator import Orchestrator
from mycroft.server.worker.blocker import restore_blockers_from_state
from mycroft.server.ws.connection_manager import manager

logger = logging.getLogger(__name__)

# ── Orchestrator registry ─────────────────────────────────────

_orchestrators: dict[str, Orchestrator] = {}


def get_orchestrator(project_id: str) -> Orchestrator | None:
    """Return the active orchestrator for a project, or None."""
    return _orchestrators.get(project_id)


def clear_orchestrators() -> None:
    """Remove all orchestrators (used in tests)."""
    _orchestrators.clear()


# ── Service name extraction ───────────────────────────────────

_SERVICE_NAME_RE = re.compile(r"^\[([^\]]+)\]")


def extract_service_name(title: str) -> str:
    """Extract service name from a Linear story title like '[Auth] Service setup'.

    Returns lowercased name, or the full title lowercased if no bracket pattern.
    """
    m = _SERVICE_NAME_RE.match(title)
    if m:
        return m.group(1).strip().lower()
    return title.strip().lower()


class ExecutionDashboardAgent(BaseAgent):
    step_id = StepId.EXECUTION

    def system_prompt(self) -> str:
        return """You are the Execution Dashboard Agent for Mycroft.

Your role is to manage the execution of code implementation by coordinating Team Lead agents.

## Commands
The user can send these commands:
- **start**: Begin execution — spawn Team Leads for each service, start processing tasks
- **pause**: Pause all Team Leads (current tasks finish, no new ones start)
- **resume**: Resume paused Team Leads
- **status**: Report current execution status (tasks queued/running/completed/failed/blocked)
- **retry <service>**: Retry failed tasks for a specific service

## Your Process
1. When the user says "start" (or equivalent), initialize the Orchestrator with Team Leads
2. Report progress as Team Leads work through their tasks
3. When blockers appear, notify the user and explain what's needed
4. Handle pause/resume/retry commands
5. When all tasks are complete, present the final report

## Important
- You are a COORDINATOR, not a coder — you don't write code, you manage the process
- Always report status changes to the user
- If a Team Lead encounters repeated failures, escalate to the user
- Blockers are resolved through Linear (the user comments on the blocker issue)
- The execution continues until all tasks are done, failed, or blocked"""

    def tools(self) -> list[dict[str, Any]]:
        return [user_confirm.TOOL_DEF]

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        if name == "user_confirm":
            return await user_confirm.execute(self.project.project_id, input_data)
        return json.dumps({"error": f"Unknown tool: {name}"})

    async def run(self, user_text: str) -> None:
        """Override run to handle execution commands directly."""
        text_lower = user_text.strip().lower()

        if text_lower == "start":
            await self._handle_start()
            return

        if text_lower == "pause":
            await self._handle_pause()
            return

        if text_lower == "resume":
            await self._handle_resume()
            return

        if text_lower == "status":
            await self._handle_status()
            return

        if text_lower.startswith("retry "):
            await self._handle_retry(text_lower[6:].strip())
            return

        await super().run(user_text)

    # ── Command handlers ──────────────────────────────────────

    async def _handle_start(self) -> None:
        """Initialize or recover the orchestrator and begin execution."""
        project_id = self.project.project_id

        if ExecutionState.exists(project_id):
            # Recover from crash
            logger.info("Found existing execution state, recovering...")
            exec_state = await recover_execution(project_id)
            restore_blockers_from_state(exec_state)

            if exec_state.pending == 0:
                logger.info("All tasks already completed, nothing to resume")
                return

            # Rebuild orchestrator from recovered state
            repo_path = Path(self.project.metadata.get("repo_path", ""))
            claude_md = self.project.metadata.get("claude_md", "")
            business_spec = self.project.metadata.get("business_spec", "")

            orchestrator = Orchestrator.from_execution_state(
                exec_state,
                repo_path=repo_path,
                claude_md=claude_md,
                business_spec=business_spec,
            )
            logger.info(
                "Resuming execution: %d succeeded, %d remaining",
                exec_state.succeeded,
                exec_state.pending,
            )
        else:
            # Fresh start — create ExecutionState from project task data
            exec_state = ExecutionState(project_id=project_id)
            await self._populate_from_linear(exec_state)
            exec_state.save()

            orchestrator = Orchestrator(project_id, execution_state=exec_state)
            logger.info("Starting fresh execution for project %s", project_id)

        # Store in registry and start
        _orchestrators[project_id] = orchestrator
        await orchestrator.start()

        # Background task: await completion, then clean up
        asyncio.create_task(self._wait_and_finalize(project_id, orchestrator))

        await manager.send(
            project_id,
            WorkerBatchUpdate(
                total_tasks=orchestrator.state.total_tasks,
                queued=orchestrator.state.queued,
                running=orchestrator.state.running,
                succeeded=orchestrator.state.succeeded,
                failed=orchestrator.state.failed,
                blocked=orchestrator.state.blocked,
            ),
        )

    async def _wait_and_finalize(
        self, project_id: str, orchestrator: Orchestrator
    ) -> None:
        """Background coroutine: wait for orchestrator to finish, then clean up."""
        try:
            results = await orchestrator.wait()
            total = sum(len(r) for r in results.values())
            logger.info(
                "Execution complete for project %s: %d results across %d services",
                project_id,
                total,
                len(results),
            )
        except Exception:
            logger.exception("Error waiting for orchestrator on project %s", project_id)
        finally:
            _orchestrators.pop(project_id, None)

    async def _handle_pause(self) -> None:
        """Pause all Team Leads."""
        project_id = self.project.project_id
        orchestrator = _orchestrators.get(project_id)
        if orchestrator is None:
            await manager.send(
                project_id,
                ErrorMessage(message="No active execution to pause."),
            )
            return
        orchestrator.pause_all()
        await manager.send(
            project_id,
            WorkerBatchUpdate(
                total_tasks=orchestrator.state.total_tasks,
                queued=orchestrator.state.queued,
                running=orchestrator.state.running,
                succeeded=orchestrator.state.succeeded,
                failed=orchestrator.state.failed,
                blocked=orchestrator.state.blocked,
            ),
        )

    async def _handle_resume(self) -> None:
        """Resume all Team Leads."""
        project_id = self.project.project_id
        orchestrator = _orchestrators.get(project_id)
        if orchestrator is None:
            await manager.send(
                project_id,
                ErrorMessage(message="No active execution to resume."),
            )
            return
        orchestrator.resume_all()
        await manager.send(
            project_id,
            WorkerBatchUpdate(
                total_tasks=orchestrator.state.total_tasks,
                queued=orchestrator.state.queued,
                running=orchestrator.state.running,
                succeeded=orchestrator.state.succeeded,
                failed=orchestrator.state.failed,
                blocked=orchestrator.state.blocked,
            ),
        )

    async def _handle_status(self) -> None:
        """Send current execution status to the client."""
        project_id = self.project.project_id
        orchestrator = _orchestrators.get(project_id)
        if orchestrator is None:
            await manager.send(
                project_id,
                ErrorMessage(message="No active execution."),
            )
            return
        status = orchestrator.get_status()
        await manager.send_json(project_id, {"type": "execution_status", **status})

    async def _handle_retry(self, service_name: str) -> None:
        """Resume a specific service (retry failed tasks)."""
        project_id = self.project.project_id
        orchestrator = _orchestrators.get(project_id)
        if orchestrator is None:
            await manager.send(
                project_id,
                ErrorMessage(message="No active execution."),
            )
            return
        found = orchestrator.resume_service(service_name)
        if not found:
            await manager.send(
                project_id,
                ErrorMessage(message=f"Service '{service_name}' not found."),
            )
            return
        await manager.send(
            project_id,
            WorkerBatchUpdate(
                total_tasks=orchestrator.state.total_tasks,
                queued=orchestrator.state.queued,
                running=orchestrator.state.running,
                succeeded=orchestrator.state.succeeded,
                failed=orchestrator.state.failed,
                blocked=orchestrator.state.blocked,
            ),
        )

    # ── Linear population ─────────────────────────────────────

    async def _populate_from_linear(self, exec_state: ExecutionState) -> None:
        """Fetch tasks from Linear and populate the ExecutionState.

        Stories (parent_id=None) become ServiceRecords.
        Tasks (parent_id set) become TaskRecords under the parent story's service.
        """
        linear_project_id = self.project.metadata.get("linear_project_id")
        if not linear_project_id:
            logger.info("No linear_project_id in metadata, skipping Linear population")
            return

        try:
            if not server_settings.linear_api_key:
                logger.info("No Linear API key configured, skipping population")
                return

            lc = LinearClient()
            issues = await lc.list_project_issues(linear_project_id)
            await lc.close()
        except Exception:
            logger.exception("Failed to fetch issues from Linear")
            return

        if not issues:
            logger.info("No issues found in Linear project %s", linear_project_id)
            return

        # Separate stories (parent_id=None) from tasks
        stories = [i for i in issues if i.parent_id is None]
        tasks = [i for i in issues if i.parent_id is not None]

        # Build story_id → service_name map
        story_service_map: dict[str, str] = {}
        for story in stories:
            svc_name = extract_service_name(story.title)
            story_service_map[story.id] = svc_name
            exec_state.services[svc_name] = ServiceRecord(
                service_name=svc_name,
                task_ids=[],
            )

        # Assign tasks to services
        for task in tasks:
            svc_name = story_service_map.get(task.parent_id or "", "")
            if not svc_name:
                logger.warning(
                    "Task %s has unknown parent %s, skipping", task.id, task.parent_id
                )
                continue

            task_record = TaskRecord(
                task_id=task.id,
                title=task.title,
                service_name=svc_name,
            )
            exec_state.tasks[task.id] = task_record
            exec_state.services[svc_name].task_ids.append(task.id)

        exec_state._recount()
        logger.info(
            "Populated from Linear: %d services, %d tasks",
            len(exec_state.services),
            len(exec_state.tasks),
        )
