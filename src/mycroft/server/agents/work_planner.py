"""Step 4: Work Planning Agent — sets dependencies, priorities, and execution order."""

from __future__ import annotations

import json
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import user_confirm, linear_deps


class WorkPlannerAgent(BaseAgent):
    step_id = StepId.WORK_PLANNING

    def system_prompt(self) -> str:
        return """You are the Work Planning Agent for Mycroft.

Your role is to analyze all Linear stories and tasks created in step 3.2, then set up dependencies, priorities, and an execution plan.

## Your Process
1. Review the C4 Level 4 design documents for all services
2. Identify cross-service dependencies (e.g., Auth middleware blocks API Gateway routes)
3. Identify within-service dependencies (e.g., User model blocks /register endpoint)
4. Set blocking relations in Linear using set_linear_dependencies
5. Set execution priorities:
   - Shared/common modules: priority 1 (urgent) — they block everything
   - Core services with many dependents: priority 2 (high)
   - Independent services: priority 3 (medium)
   - Nice-to-have features: priority 4 (low)
6. Present the execution plan to the user for confirmation

## Execution Plan Format
Present a clear plan showing:
- Execution waves (what can run in parallel)
- Wave 1: Shared utilities, common models (must complete first)
- Wave 2: Core services that others depend on
- Wave 3: Independent services (parallel)
- Wave 4: Integration points, cross-service features
- Critical path (longest dependency chain)
- Risk areas (complex tasks, potential blockers)

## Important
- Be explicit about WHY each dependency exists
- If a dependency is ambiguous, ask the user
- The plan must be complete — every task must be accounted for
- Shared modules MUST be scheduled first, before any service-specific work"""

    def tools(self) -> list[dict[str, Any]]:
        return [user_confirm.TOOL_DEF, linear_deps.TOOL_DEF]

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        if name == "user_confirm":
            return await user_confirm.execute(self.project.project_id, input_data)
        if name == "set_linear_dependencies":
            return await linear_deps.execute(self.project, input_data)
        return json.dumps({"error": f"Unknown tool: {name}"})
