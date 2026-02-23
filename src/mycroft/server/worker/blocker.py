"""Blocker lifecycle — create Linear issue, pause service, wait for resolution.

Same asyncio.Event-based pattern as user_confirm.py, but for execution blockers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from mycroft.server.linear.client import LinearClient
from mycroft.server.linear.models import LinearIssueCreateInput
from mycroft.server.settings import settings
from mycroft.server.ws.connection_manager import manager
from mycroft.shared.protocol import BlockerNotification

logger = logging.getLogger(__name__)


class PendingBlocker:
    def __init__(
        self,
        blocker_id: str,
        service_name: str,
        question: str,
        linear_issue_id: str = "",
        linear_issue_url: str = "",
    ) -> None:
        self.blocker_id = blocker_id
        self.service_name = service_name
        self.question = question
        self.linear_issue_id = linear_issue_id
        self.linear_issue_url = linear_issue_url
        self.event = asyncio.Event()
        self.answer: str = ""


# Active blockers: blocker_id → PendingBlocker
_blockers: dict[str, PendingBlocker] = {}


def get_pending_blockers() -> dict[str, PendingBlocker]:
    """Get all active blockers (for status reporting)."""
    return dict(_blockers)


def get_blocker(blocker_id: str) -> PendingBlocker | None:
    return _blockers.get(blocker_id)


async def create_blocker(
    project_id: str,
    service_name: str,
    question: str,
    context: str = "",
) -> PendingBlocker:
    """Create a blocker: Linear issue + pause mechanism.

    Returns a PendingBlocker whose .event can be awaited.
    """
    blocker_id = uuid.uuid4().hex[:8]

    linear_issue_id = ""
    linear_issue_url = ""

    # Create Linear issue if configured
    if settings.linear_api_key and settings.linear_team_id:
        try:
            lc = LinearClient()
            description = f"## Blocker\n\n**Service**: {service_name}\n\n**Question**: {question}"
            if context:
                description += f"\n\n**Context**: {context}"
            description += "\n\n---\n*Reply in a comment to resolve this blocker.*"

            issue = await lc.create_issue(
                LinearIssueCreateInput(
                    title=f"[{service_name}] BLOCKER: {question[:80]}",
                    description=description,
                    team_id=settings.linear_team_id,
                    priority=1,  # urgent
                )
            )
            linear_issue_id = issue.id
            linear_issue_url = issue.url
            logger.info(
                "Created blocker Linear issue %s for service %s",
                issue.identifier,
                service_name,
            )
            await lc.close()
        except Exception:
            logger.exception("Failed to create blocker Linear issue")

    blocker = PendingBlocker(
        blocker_id=blocker_id,
        service_name=service_name,
        question=question,
        linear_issue_id=linear_issue_id,
        linear_issue_url=linear_issue_url,
    )
    _blockers[blocker_id] = blocker

    # Notify client
    await manager.send(
        project_id,
        BlockerNotification(
            blocker_id=blocker_id,
            service_name=service_name,
            question=question,
            linear_issue_url=linear_issue_url,
        ),
    )

    logger.info(
        "Blocker %s created for service %s: %s",
        blocker_id,
        service_name,
        question,
    )
    return blocker


def resolve_blocker(blocker_id: str, answer: str) -> bool:
    """Resolve a blocker with the user's answer. Returns True if found."""
    blocker = _blockers.get(blocker_id)
    if blocker is None:
        logger.warning("No blocker found with id %s", blocker_id)
        return False

    blocker.answer = answer
    blocker.event.set()
    logger.info("Resolved blocker %s with answer: %s", blocker_id, answer[:100])
    return True


def resolve_blocker_by_linear_issue(linear_issue_id: str, answer: str) -> bool:
    """Resolve a blocker by its Linear issue ID (called from webhook)."""
    for blocker in _blockers.values():
        if blocker.linear_issue_id == linear_issue_id:
            return resolve_blocker(blocker.blocker_id, answer)
    logger.warning("No blocker found for Linear issue %s", linear_issue_id)
    return False


def cleanup_blocker(blocker_id: str) -> None:
    """Remove a blocker from the registry after processing."""
    _blockers.pop(blocker_id, None)


def clear_all_blockers() -> None:
    """Clear all blockers (used in tests and shutdown)."""
    _blockers.clear()
