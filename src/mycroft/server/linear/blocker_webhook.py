"""Webhook handler: resolve blockers when a comment is added to a Linear issue."""

from __future__ import annotations

import logging

from mycroft.server.linear.models import LinearWebhookPayload
from mycroft.server.linear.webhook import on_linear_event
from mycroft.server.worker.blocker import resolve_blocker_by_linear_issue

logger = logging.getLogger(__name__)


@on_linear_event("create", "Comment")
async def handle_comment_created(payload: LinearWebhookPayload) -> None:
    """When a comment is created on a Linear issue, check if it resolves a blocker."""
    issue_id = payload.data.get("issueId", "") or payload.data.get("issue", {}).get("id", "")
    body = payload.data.get("body", "")

    if not issue_id:
        logger.debug("Comment webhook missing issueId, skipping")
        return

    resolved = resolve_blocker_by_linear_issue(issue_id, body)
    if resolved:
        logger.info("Blocker resolved via webhook comment on issue %s", issue_id)
    else:
        logger.debug("No matching blocker for comment on issue %s", issue_id)
