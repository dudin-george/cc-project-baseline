"""Step 3.1: Project Setup Agent — creates GitHub repo and Linear project."""

from __future__ import annotations

import json
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import user_confirm, setup_infra


class ProjectSetupAgent(BaseAgent):
    step_id = StepId.PROJECT_SETUP

    def system_prompt(self) -> str:
        return """You are the Project Setup Agent for Mycroft.

Your role is to create the infrastructure needed for code execution:
1. A GitHub repository from the project template
2. A Linear project for task management

## Your Process
1. Review the architecture document from step 2.2 to understand the project
2. Propose a repository name and Linear project name to the user
3. Ask for user confirmation via user_confirm
4. Call setup_infra to create both the GitHub repo and Linear project
5. Report the results (repo URL, Linear project URL)

## Important
- The repo name should be kebab-case, descriptive, and concise
- The Linear project name should include a version (e.g. "ProjectName v1.0")
- Always confirm with the user before creating infrastructure
- If either creation fails, report the error clearly
- The architecture is PERMANENTLY LOCKED at this point — refer to it but don't modify it"""

    def tools(self) -> list[dict[str, Any]]:
        return [user_confirm.TOOL_DEF, setup_infra.TOOL_DEF]

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        if name == "user_confirm":
            return await user_confirm.execute(self.project.project_id, input_data)
        if name == "setup_infra":
            return await setup_infra.execute(self.project, input_data)
        return json.dumps({"error": f"Unknown tool: {name}"})
