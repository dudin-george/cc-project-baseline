"""API key validation for WebSocket connections."""

from __future__ import annotations

from mycroft.server.settings import settings


def validate_api_key(api_key: str) -> bool:
    return settings.validate_api_key(api_key)
