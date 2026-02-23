"""Linear dependencies tool — set blocking relations and priorities between issues."""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.server.linear.client import LinearClient
from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "set_linear_dependencies",
    "description": (
        "Set blocking relations and priorities between Linear issues. "
        "Use this to define task ordering: which tasks must complete before others can start. "
        "Also sets priority levels for execution ordering."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dependencies": {
                "type": "array",
                "description": "List of blocking relations to create.",
                "items": {
                    "type": "object",
                    "properties": {
                        "blocker_id": {
                            "type": "string",
                            "description": "ID of the issue that blocks (must complete first).",
                        },
                        "blocked_id": {
                            "type": "string",
                            "description": "ID of the issue that is blocked (waits for blocker).",
                        },
                    },
                    "required": ["blocker_id", "blocked_id"],
                },
            },
            "priority_updates": {
                "type": "array",
                "description": "Optional list of priority updates for issues.",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string"},
                        "priority": {
                            "type": "integer",
                            "description": "0=none, 1=urgent, 2=high, 3=medium, 4=low.",
                        },
                    },
                    "required": ["issue_id", "priority"],
                },
                "default": [],
            },
        },
        "required": ["dependencies"],
    },
}


async def execute(project: ProjectState, input_data: dict[str, Any]) -> str:
    deps = input_data["dependencies"]
    priority_updates = input_data.get("priority_updates", [])

    lc = LinearClient()
    created_relations = 0
    updated_priorities = 0
    errors: list[str] = []

    try:
        # Create blocking relations
        for dep in deps:
            try:
                await lc.create_issue_relation(
                    dep["blocker_id"], dep["blocked_id"], "blocks"
                )
                created_relations += 1
                logger.info(
                    "Created relation: %s blocks %s",
                    dep["blocker_id"],
                    dep["blocked_id"],
                )
            except Exception as e:
                msg = f"Failed to create relation {dep['blocker_id']} -> {dep['blocked_id']}: {e}"
                logger.warning(msg)
                errors.append(msg)

        # Update priorities using issue state update (priority field)
        # Note: Linear's issueUpdate supports priority directly
        for upd in priority_updates:
            try:
                query = """
                mutation($id: String!, $input: IssueUpdateInput!) {
                    issueUpdate(id: $id, input: $input) { success }
                }
                """
                await lc._request(
                    query,
                    {"id": upd["issue_id"], "input": {"priority": upd["priority"]}},
                )
                updated_priorities += 1
            except Exception as e:
                msg = f"Failed to update priority for {upd['issue_id']}: {e}"
                logger.warning(msg)
                errors.append(msg)
    finally:
        await lc.close()

    return json.dumps({
        "relations_created": created_relations,
        "priorities_updated": updated_priorities,
        "errors": errors,
    })
