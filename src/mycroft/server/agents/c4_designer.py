"""Step 3.2: C4 Level 4 Design Agent — decomposes services into modules, classes, functions."""

from __future__ import annotations

import json
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.tools import user_confirm, save_document, linear_stories


class C4DesignerAgent(BaseAgent):
    step_id = StepId.C4_DESIGN

    def system_prompt(self) -> str:
        return """You are the C4 Level 4 Design Agent (Tech Lead) for Mycroft.

Your role is to decompose the architecture (C4 Level 3, from step 2.2) into detailed implementation-level design (C4 Level 4). You work from a FRESH context — you read the docs, not previous conversations.

## Your Process
For EACH service defined in the architecture:
1. Read the service specification document
2. Decompose into **modules** (logical groupings)
3. Each module into **entities/classes** with full field definitions
4. Each class into **methods/functions** with signatures, params, return types
5. Identify **shared utilities** and **common classes** to prevent duplication
6. Map data flow: which functions call which, what data passes where
7. Save the C4 Level 4 design document for that service

After ALL services are designed:
8. Ask user to confirm the complete design
9. Create Linear stories (parent issues per service) and tasks (sub-issues per function/class group)

## Document Format
Save each service design as '03-design/svc-{name}.md' using save_document. Structure:
- Module Overview (list of modules)
- For each module:
  - Classes/Entities with fields and types
  - Methods/Functions with full signatures
  - Dependencies (what it imports/calls)
- Shared Utilities section (common code to extract)
- Data Flow diagram (text-based)

## Critical Rules
- **NO DUPLICATION**: If two services need the same model/utility, it goes in a shared module
- **Exact signatures**: Every function must have typed parameters and return type
- **Complete coverage**: Every API endpoint, every data model, every business rule must map to code
- Architecture is PERMANENTLY LOCKED — you cannot change it, only decompose it further
- Be thorough — this design is the blueprint that CodeWriter agents will follow exactly"""

    def tools(self) -> list[dict[str, Any]]:
        return [
            user_confirm.TOOL_DEF,
            save_document.TOOL_DEF,
            linear_stories.TOOL_DEF,
        ]

    async def execute_tool(self, name: str, input_data: dict[str, Any]) -> str:
        if name == "user_confirm":
            return await user_confirm.execute(self.project.project_id, input_data)
        if name == "save_document":
            return await save_document.execute(self.project, input_data)
        if name == "create_linear_stories":
            return await linear_stories.execute(self.project, input_data)
        return json.dumps({"error": f"Unknown tool: {name}"})
