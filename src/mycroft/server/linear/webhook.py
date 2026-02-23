"""FastAPI router for Linear webhook events."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from mycroft.server.linear.models import LinearWebhookPayload
from mycroft.server.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Registry of event handlers: key = (action, type), value = list of async callables.
_handlers: dict[tuple[str, str], list[Callable[[LinearWebhookPayload], Awaitable[None]]]] = {}


def on_linear_event(
    action: str, resource_type: str
) -> Callable[[Callable[[LinearWebhookPayload], Awaitable[None]]], Callable[[LinearWebhookPayload], Awaitable[None]]]:
    """Decorator to register a handler for a specific Linear event.

    Usage:
        @on_linear_event("update", "Issue")
        async def handle_issue_update(payload: LinearWebhookPayload):
            ...
    """
    def decorator(fn: Callable[[LinearWebhookPayload], Awaitable[None]]) -> Callable[[LinearWebhookPayload], Awaitable[None]]:
        key = (action, resource_type)
        _handlers.setdefault(key, []).append(fn)
        return fn
    return decorator


def register_handler(
    action: str,
    resource_type: str,
    handler: Callable[[LinearWebhookPayload], Awaitable[None]],
) -> None:
    """Programmatic handler registration (for use without decorators)."""
    key = (action, resource_type)
    _handlers.setdefault(key, []).append(handler)


def clear_handlers() -> None:
    """Remove all registered handlers (used in tests)."""
    _handlers.clear()


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/linear")
async def linear_webhook(
    request: Request,
    linear_signature: str = Header(None, alias="linear-signature"),
) -> dict[str, Any]:
    body = await request.body()

    # Verify signature if secret is configured.
    if settings.linear_webhook_secret:
        if not linear_signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        if not _verify_signature(body, linear_signature, settings.linear_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    payload = LinearWebhookPayload(**data)
    logger.info("Linear webhook: action=%s type=%s", payload.action, payload.type)

    key = (payload.action, payload.type)
    handlers = _handlers.get(key, [])
    for handler in handlers:
        try:
            await handler(payload)
        except Exception:
            logger.exception("Error in Linear webhook handler for %s", key)

    return {"status": "ok"}
