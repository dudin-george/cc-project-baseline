"""Execution state persistence — crash recovery for the worker system.

Checkpoints every task completion to disk so the orchestrator can resume
after a crash without re-executing completed work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from mycroft.server.settings import settings
from mycroft.server.state.persistence import atomic_json_write, json_read

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    succeeded = "succeeded"
    failed = "failed"
    blocked = "blocked"


class SubAgentRecord(BaseModel):
    agent_type: str  # "code_writer", "unit_tester", "qa_tester"
    success: bool
    output: str = ""  # truncated to 2000 chars
    error: str = ""


class TaskRecord(BaseModel):
    task_id: str
    title: str
    service_name: str
    status: TaskStatus = TaskStatus.pending
    pr_url: str = ""
    error: str = ""
    sub_agent_results: list[SubAgentRecord] = Field(default_factory=list)
    attempts: int = 0
    started_at: str = ""
    completed_at: str = ""


class BlockerRecord(BaseModel):
    blocker_id: str
    service_name: str
    question: str
    linear_issue_id: str = ""
    linear_issue_url: str = ""
    resolved: bool = False
    answer: str = ""


class ServiceRecord(BaseModel):
    service_name: str
    task_ids: list[str] = Field(default_factory=list)  # ordered
    completed_task_ids: list[str] = Field(default_factory=list)
    current_task_id: str = ""
    paused: bool = False


class ExecutionState(BaseModel):
    project_id: str
    started_at: str = ""
    updated_at: str = ""
    tasks: dict[str, TaskRecord] = Field(default_factory=dict)
    services: dict[str, ServiceRecord] = Field(default_factory=dict)
    blockers: dict[str, BlockerRecord] = Field(default_factory=dict)
    total_tasks: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    # ── Persistence ──────────────────────────────────────────

    def save(self) -> None:
        self.updated_at = _now()
        path = settings.projects_dir / self.project_id / "execution.json"
        atomic_json_write(path, self.model_dump())

    @classmethod
    def load(cls, project_id: str) -> ExecutionState:
        path = settings.projects_dir / project_id / "execution.json"
        data = json_read(path)
        state = cls.model_validate(data)
        state._recount()
        return state

    @classmethod
    def exists(cls, project_id: str) -> bool:
        return (settings.projects_dir / project_id / "execution.json").exists()

    # ── Checkpoint methods ───────────────────────────────────

    def checkpoint_task_started(self, task_id: str) -> None:
        """Mark a task as in-progress. No disk write — just in-memory."""
        task = self.tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus.in_progress
        task.started_at = _now()
        task.attempts += 1
        service = self.services.get(task.service_name)
        if service:
            service.current_task_id = task_id

    def checkpoint_task_completed(
        self,
        task_id: str,
        success: bool,
        pr_url: str = "",
        error: str = "",
        sub_agent_results: list[SubAgentRecord] | None = None,
    ) -> None:
        """Mark a task as succeeded/failed and persist to disk."""
        task = self.tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus.succeeded if success else TaskStatus.failed
        task.completed_at = _now()
        task.pr_url = pr_url
        task.error = error
        if sub_agent_results:
            task.sub_agent_results = sub_agent_results

        service = self.services.get(task.service_name)
        if service:
            if success and task_id not in service.completed_task_ids:
                service.completed_task_ids.append(task_id)
            service.current_task_id = ""

        self._recount()
        self.save()

    def checkpoint_blocker_created(
        self,
        blocker_id: str,
        service_name: str,
        question: str,
        linear_issue_id: str = "",
        linear_issue_url: str = "",
    ) -> None:
        """Record a new blocker and persist to disk."""
        self.blockers[blocker_id] = BlockerRecord(
            blocker_id=blocker_id,
            service_name=service_name,
            question=question,
            linear_issue_id=linear_issue_id,
            linear_issue_url=linear_issue_url,
        )
        self.save()

    def checkpoint_blocker_resolved(
        self,
        blocker_id: str,
        answer: str,
    ) -> None:
        """Mark a blocker as resolved and persist to disk."""
        blocker = self.blockers.get(blocker_id)
        if blocker is None:
            return
        blocker.resolved = True
        blocker.answer = answer
        self.save()

    # ── Query methods ────────────────────────────────────────

    def get_pending_task_ids(self, service_name: str) -> list[str]:
        """Ordered list of task IDs not yet completed for a service."""
        service = self.services.get(service_name)
        if service is None:
            return []
        return [
            tid for tid in service.task_ids
            if tid in self.tasks
            and self.tasks[tid].status in (TaskStatus.pending, TaskStatus.blocked)
        ]

    def get_tasks_needing_requeue(self) -> list[str]:
        """Find tasks that were in-progress when the crash happened."""
        return [
            tid for tid, task in self.tasks.items()
            if task.status == TaskStatus.in_progress
        ]

    # ── Internal helpers ─────────────────────────────────────

    def _recount(self) -> None:
        """Recompute summary counters from task statuses."""
        self.succeeded = sum(
            1 for t in self.tasks.values() if t.status == TaskStatus.succeeded
        )
        self.failed = sum(
            1 for t in self.tasks.values() if t.status == TaskStatus.failed
        )
        self.pending = sum(
            1 for t in self.tasks.values()
            if t.status in (TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked)
        )
        self.total_tasks = len(self.tasks)


# ── Recovery ─────────────────────────────────────────────────


async def recover_execution(project_id: str) -> ExecutionState:
    """Load execution state, reset crashed tasks, reconcile blockers.

    Returns the recovered state ready for the orchestrator.
    """
    state = ExecutionState.load(project_id)

    # Reset in-progress tasks back to pending (they were interrupted)
    requeue = state.get_tasks_needing_requeue()
    for task_id in requeue:
        task = state.tasks[task_id]
        task.status = TaskStatus.pending
        task.started_at = ""
        task.completed_at = ""
        # Also clear the service's current_task_id
        service = state.services.get(task.service_name)
        if service and service.current_task_id == task_id:
            service.current_task_id = ""
        logger.info("Reset interrupted task %s to pending", task_id)

    # Reconcile blockers — check Linear for comments on unresolved blockers
    unresolved = [
        b for b in state.blockers.values()
        if not b.resolved and b.linear_issue_id
    ]
    if unresolved:
        await _reconcile_blockers(state, unresolved)

    state._recount()
    state.save()

    logger.info(
        "Recovered execution state for project %s: %d succeeded, %d pending, %d requeued",
        project_id,
        state.succeeded,
        state.pending,
        len(requeue),
    )
    return state


async def _reconcile_blockers(
    state: ExecutionState,
    unresolved: list[BlockerRecord],
) -> None:
    """Check Linear for comments that may have resolved blockers while we were down."""
    from mycroft.server.linear.client import LinearClient

    if not settings.linear_api_key:
        return

    try:
        lc = LinearClient()
        for blocker in unresolved:
            try:
                comments = await lc.get_issue_comments(blocker.linear_issue_id)
                if comments:
                    # Use the latest comment as the answer
                    blocker.resolved = True
                    blocker.answer = comments[-1].body
                    logger.info(
                        "Blocker %s resolved via Linear comment during recovery",
                        blocker.blocker_id,
                    )
            except Exception:
                logger.warning(
                    "Failed to check Linear for blocker %s", blocker.blocker_id
                )
        await lc.close()
    except Exception:
        logger.exception("Failed to reconcile blockers with Linear")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
