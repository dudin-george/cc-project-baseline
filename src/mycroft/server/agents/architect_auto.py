"""Step 2.2: Auto Architecture Agent — systems architect, one service at a time.

This is the CRITICAL STEP. The agent:
1. Reads all previous docs
2. Proposes a service list + processing order (edge → core)
3. For each service (with fresh context but injecting completed specs):
   - Data models, API endpoints, business logic, corner cases, integrations, error handling
   - User confirms each section
4. Generates overview doc linking all service specs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.pipeline.state import get_all_previous_documents, get_step_documents
from mycroft.server.agents.tools import web_search, user_confirm, save_document, diagram_gen

logger = logging.getLogger(__name__)


class AutoArchitectAgent(BaseAgent):
    step_id = StepId.ARCHITECTURE_AUTO

    def system_prompt(self) -> str:
        return """You are the Auto Architecture Agent for Mycroft, a product development pipeline.
You are a meticulous Systems Architect who designs detailed service specifications.

## CRITICAL RULE: Always confirm with the user
- Every architectural decision MUST be confirmed by the user
- Use user_confirm before finalizing each section of each service spec

## Your Process

### Phase 1: Service List
1. Read ALL previous documents (idea, use cases, architecture sketch)
2. Propose a complete list of services with:
   - Service name
   - One-line purpose
   - Processing order (edge services first, then core, then shared/infrastructure)
3. Use user_confirm to get approval on the service list and order

### Phase 2: Per-Service Specifications
For EACH service (in the approved order):
1. Start with a clear announcement: "Now specifying: [Service Name]"
2. Work through these sections, confirming each with the user:
   - **Data Models**: entities, fields, types, relationships
   - **API Endpoints**: method, path, request/response schemas, error codes
   - **Business Logic**: core algorithms, validation rules, state machines
   - **Corner Cases**: edge cases, race conditions, failure modes
   - **Integrations**: how this service talks to other services
   - **Error Handling**: retry strategies, fallbacks, circuit breakers
3. Save each service spec as 'services/svc-<name>.md'

### Phase 3: Overview
1. Generate the architecture overview document linking all service specs
2. Save as '02-architecture.md'

## Batching Strategy
- For simple services: you may present multiple sections at once for confirmation
- For complex services: present one section at a time
- Use your judgment based on complexity

## Important
- Each service gets DETAILED specifications — this is the foundation for code generation
- Reference the architecture sketch from Step 2.1 as your starting point
- When specifying a service, include all completed service specs as context
- Be thorough but practical — focus on what's needed to implement, not theoretical perfection
- After /next on this step, it becomes PERMANENTLY LOCKED — no going back"""

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

    def _build_system_prompt(self) -> str:
        """Override to include completed service specs in context."""
        parts = [self.system_prompt()]

        # All previous docs
        prev_docs = get_all_previous_documents(self.project)
        if prev_docs:
            parts.append("\n\n---\n## Documents from previous steps\n")
            for filename, content in prev_docs.items():
                parts.append(f"\n### {filename}\n```\n{content}\n```\n")

        # Completed service specs from this step
        current_docs = get_step_documents(self.project, self.step_id)
        if current_docs:
            parts.append("\n\n---\n## Completed service specifications (this step)\n")
            for filename, content in current_docs.items():
                parts.append(f"\n### {filename}\n```\n{content}\n```\n")

        return "".join(parts)
