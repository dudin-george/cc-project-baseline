"""Orchestrator — manages all Team Leads, routes events, broadcasts status."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mycroft.server.settings import settings
from mycroft.server.worker.team_lead import TaskResult, TeamLead
from mycroft.server.ws.connection_manager import manager
from mycroft.shared.protocol import WorkerBatchUpdate, WorkerStatusUpdate

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorState:
    total_tasks: int = 0
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    blocked: int = 0


class Orchestrator:
    """Manages all Team Leads for a project's execution phase."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self._leads: dict[str, TeamLead] = {}
        self._tasks: dict[str, asyncio.Task[list[TaskResult]]] = {}
        self._semaphore = asyncio.Semaphore(settings.worker_max_concurrent_leads)
        self.state = OrchestratorState()
        self._shutdown = False

    def add_team_lead(self, lead: TeamLead) -> None:
        self._leads[lead.service_name] = lead
        self.state.total_tasks += len(lead.state.tasks)
        self.state.queued += len(lead.state.tasks)

    async def start(self) -> None:
        """Start all Team Leads (bounded by semaphore)."""
        logger.info(
            "Starting orchestrator for project %s with %d services",
            self.project_id,
            len(self._leads),
        )

        for name, lead in self._leads.items():
            task = asyncio.create_task(self._run_lead(name, lead))
            self._tasks[name] = task

        await self._broadcast_batch()

    async def _run_lead(self, name: str, lead: TeamLead) -> list[TaskResult]:
        """Run a Team Lead under the concurrency semaphore."""
        async with self._semaphore:
            if self._shutdown:
                return []

            logger.info("Team Lead [%s] starting", name)
            self.state.running += min(len(lead.state.tasks), 1)
            self.state.queued = max(0, self.state.queued - len(lead.state.tasks))
            await self._broadcast_batch()

            try:
                results = await lead.run()

                for r in results:
                    if r.success:
                        self.state.succeeded += 1
                    else:
                        self.state.failed += 1
                    self.state.running = max(0, self.state.running - 1)

                    await manager.send(
                        self.project_id,
                        WorkerStatusUpdate(
                            task_id=r.task_id,
                            task_title=r.task_title,
                            service_name=name,
                            worker_id=name,
                            status="succeeded" if r.success else "failed",
                            pr_url=r.pr_url,
                            error=r.error,
                        ),
                    )
                    await self._broadcast_batch()

                logger.info("Team Lead [%s] finished: %d results", name, len(results))
                return results

            except Exception:
                logger.exception("Team Lead [%s] crashed", name)
                self.state.running = max(0, self.state.running - 1)
                self.state.failed += len(lead.state.tasks)
                await self._broadcast_batch()
                return []

    async def _broadcast_batch(self) -> None:
        """Send batch status update to client."""
        await manager.send(
            self.project_id,
            WorkerBatchUpdate(
                total_tasks=self.state.total_tasks,
                queued=self.state.queued,
                running=self.state.running,
                succeeded=self.state.succeeded,
                failed=self.state.failed,
                blocked=self.state.blocked,
            ),
        )

    async def wait(self) -> dict[str, list[TaskResult]]:
        """Wait for all Team Leads to complete. Returns results by service."""
        results: dict[str, list[TaskResult]] = {}
        for name, task in self._tasks.items():
            try:
                results[name] = await task
            except Exception:
                logger.exception("Error waiting for Team Lead [%s]", name)
                results[name] = []
        return results

    def pause_all(self) -> None:
        for lead in self._leads.values():
            lead.pause()
        logger.info("All Team Leads paused")

    def resume_all(self) -> None:
        for lead in self._leads.values():
            lead.resume()
        logger.info("All Team Leads resumed")

    def pause_service(self, service_name: str) -> bool:
        lead = self._leads.get(service_name)
        if lead:
            lead.pause()
            return True
        return False

    def resume_service(self, service_name: str) -> bool:
        lead = self._leads.get(service_name)
        if lead:
            lead.resume()
            return True
        return False

    async def shutdown(self) -> None:
        """Cancel all Team Leads and clean up."""
        self._shutdown = True
        for lead in self._leads.values():
            lead.cancel()
        for task in self._tasks.values():
            task.cancel()
        logger.info("Orchestrator shut down for project %s", self.project_id)

    def get_status(self) -> dict[str, Any]:
        """Get current execution status."""
        services: dict[str, Any] = {}
        for name, lead in self._leads.items():
            services[name] = {
                "current_task": lead.state.current_task,
                "paused": lead.state.paused,
                "completed": len(lead.state.completed),
                "total": len(lead.state.tasks),
                "cancelled": lead.state.cancelled,
            }
        return {
            "total_tasks": self.state.total_tasks,
            "queued": self.state.queued,
            "running": self.state.running,
            "succeeded": self.state.succeeded,
            "failed": self.state.failed,
            "blocked": self.state.blocked,
            "services": services,
        }
