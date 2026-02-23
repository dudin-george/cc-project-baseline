"""Step 5: Execution Dashboard Agent — manages Team Leads and worker orchestration.

Unlike other agents, this one does NOT follow the standard conversation loop.
It interprets commands (start, pause, resume, status) and manages the Orchestrator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import user_confirm
from mycroft.server.worker.execution_state import ExecutionState, TaskRecord, ServiceRecord, recover_execution
from mycroft.server.worker.orchestrator import Orchestrator
from mycroft.server.worker.blocker import restore_blockers_from_state

logger = logging.getLogger(__name__)


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
        """Override run to handle execution commands.

        For now, delegates to the base conversation loop.
        The actual orchestrator integration happens in Phase 6.
        """
        text_lower = user_text.strip().lower()

        if text_lower == "start":
            await self._handle_start()
            return

        # Route execution commands to orchestrator (Phase 6)
        if text_lower in ("pause", "resume", "status") or text_lower.startswith("retry"):
            # Phase 6 will add orchestrator routing here.
            # For now, fall through to the conversational agent.
            pass

        await super().run(user_text)

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

            # Phase 6 will populate tasks/services from Linear data here.
            # For now, save the empty state as a checkpoint marker.
            exec_state.save()

            orchestrator = Orchestrator(project_id, execution_state=exec_state)
            logger.info("Starting fresh execution for project %s", project_id)
