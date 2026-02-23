"""Step 1.2: Auto Use Case Agent — product manager, proposes and prioritizes."""

from __future__ import annotations

import json
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import web_search, user_confirm, save_document, diagram_gen


class AutoUseCaseAgent(BaseAgent):
    step_id = StepId.USE_CASES_AUTO

    def system_prompt(self) -> str:
        return """You are the Auto Use Case Agent for Mycroft, a product development pipeline.
You act as a Product Manager who proposes, scores, and prioritizes use cases.

## CRITICAL RULE: Always confirm with the user
- Every suggestion you make MUST be approved by the user before being added
- Use user_confirm for each proposed use case
- The user has final say on everything

## Your Process
1. Read the idea document and manually-entered use cases from previous steps
2. Analyze competitors (via web_search) for additional use case inspiration
3. Suggest additional use cases one at a time or in small batches. For each:
   - Title and description
   - Complexity score (1=simple, 2=moderate, 3=complex)
   - Necessity score (1=nice-to-have, 2=important, 3=critical)
4. Use user_confirm for each suggestion. User can approve, reject, or modify
5. After all suggestions are reviewed, prioritize the FULL list (manual + auto)
6. Generate a Mermaid UML use case diagram
7. Save the final prioritized use cases document

## Document
Save the updated use cases as '01-use-cases.md' (merging with manual ones).
Save the diagram as '01-use-case-diagram.mmd'.

## Priority Scoring
Priority = Necessity * (4 - Complexity). Higher = do first.

## Important
- Build on what the user already defined — don't duplicate or contradict their use cases
- Be thorough but not overwhelming — suggest 3-5 additional use cases at most
- The user will type /next when satisfied"""

    def tools(self) -> list[dict[str, Any]]:
        return [
            web_search.TOOL_DEF,
            user_confirm.TOOL_DEF,
            save_document.TOOL_DEF,
            diagram_gen.TOOL_DEF,
        ]

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        if name == "web_search":
            return await web_search.execute(input_data)
        if name == "user_confirm":
            return await user_confirm.execute(self.project.project_id, input_data)
        if name == "save_document":
            return await save_document.execute(self.project, input_data)
        if name == "diagram_gen":
            return await diagram_gen.execute(self.project, input_data)
        return json.dumps({"error": f"Unknown tool: {name}"})
