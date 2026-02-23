"""User confirmation tool — asyncio.Event-based blocking for user input.

When an agent calls user_confirm, the server:
1. Sends a confirm_request to the client
2. Blocks the agent loop (via asyncio.Event)
3. When client responds with confirm_response, resolves the event
4. Agent continues with the user's answer
"""

from __future__ import annotations

import asyncio
import uuid
import logging
from typing import Any

from mycroft.shared.protocol import ConfirmRequest
from mycroft.server.ws.connection_manager import manager

logger = logging.getLogger(__name__)


class PendingConfirm:
    def __init__(self, confirm_id: str, prompt: str, context: str) -> None:
        self.confirm_id = confirm_id
        self.prompt = prompt
        self.context = context
        self.event = asyncio.Event()
        self.approved: bool = False
        self.comment: str = ""


# Active pending confirms: project_id → PendingConfirm
_pending: dict[str, PendingConfirm] = {}


TOOL_DEF: dict[str, Any] = {
    "name": "user_confirm",
    "description": (
        "Ask the user to confirm or provide input on a decision. "
        "Use this when you need explicit user approval before proceeding, "
        "such as confirming a proposed use case, architecture decision, or document update. "
        "The agent will be blocked until the user responds."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The question or decision to present to the user.",
            },
            "context": {
                "type": "string",
                "description": "Additional context to help the user decide (optional).",
                "default": "",
            },
        },
        "required": ["prompt"],
    },
}


async def execute(project_id: str, input_data: dict[str, Any]) -> str:
    """Send confirm request to client and block until response."""
    confirm_id = uuid.uuid4().hex[:8]
    prompt = input_data["prompt"]
    context = input_data.get("context", "")

    pending = PendingConfirm(confirm_id, prompt, context)
    _pending[project_id] = pending

    # Send confirm request to client
    await manager.send(
        project_id,
        ConfirmRequest(confirm_id=confirm_id, prompt=prompt, context=context),
    )

    logger.info("Waiting for user confirmation %s in project %s", confirm_id, project_id)

    # Block until user responds
    await pending.event.wait()

    # Clean up
    _pending.pop(project_id, None)

    result = {
        "approved": pending.approved,
        "comment": pending.comment,
    }

    import json
    return json.dumps(result)


def resolve_confirm(
    project_id: str, confirm_id: str, approved: bool, comment: str
) -> None:
    """Called when client sends confirm_response."""
    pending = _pending.get(project_id)
    if pending is None or pending.confirm_id != confirm_id:
        logger.warning(
            "No matching pending confirm for %s/%s", project_id, confirm_id
        )
        return

    pending.approved = approved
    pending.comment = comment
    pending.event.set()


def get_pending_confirm(project_id: str) -> ConfirmRequest | None:
    """Get pending confirm request for reconnection."""
    pending = _pending.get(project_id)
    if pending is None:
        return None
    return ConfirmRequest(
        confirm_id=pending.confirm_id,
        prompt=pending.prompt,
        context=pending.context,
    )
