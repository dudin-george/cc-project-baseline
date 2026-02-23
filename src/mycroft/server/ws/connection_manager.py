"""Track active WebSocket connections per project."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from mycroft.shared.protocol import ServerMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}  # project_id → websocket
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        async with self._lock:
            existing = self._connections.get(project_id)
            if existing:
                logger.warning("Replacing existing connection for project %s", project_id)
                try:
                    await existing.close(code=4001, reason="Replaced by new connection")
                except Exception:
                    pass
            self._connections[project_id] = ws

    async def disconnect(self, project_id: str) -> None:
        async with self._lock:
            self._connections.pop(project_id, None)

    async def send(self, project_id: str, message: ServerMessage) -> bool:
        ws = self._connections.get(project_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message.model_dump())
            return True
        except Exception:
            logger.exception("Failed to send message to project %s", project_id)
            await self.disconnect(project_id)
            return False

    async def send_json(self, project_id: str, data: dict[str, Any]) -> bool:
        ws = self._connections.get(project_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception:
            logger.exception("Failed to send JSON to project %s", project_id)
            await self.disconnect(project_id)
            return False

    def is_connected(self, project_id: str) -> bool:
        return project_id in self._connections


manager = ConnectionManager()
