"""Bridge Anthropic streaming events to WebSocket protocol messages."""

from __future__ import annotations

import logging

from mycroft.shared.protocol import (
    TextBlockStart,
    TextBlockEnd,
    TextDelta,
    ToolActivity,
)
from mycroft.server.ws.connection_manager import manager

logger = logging.getLogger(__name__)


class StreamRelay:
    """Relays Anthropic streaming events to a WebSocket client."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self._in_text_block = False

    async def on_text_start(self) -> None:
        self._in_text_block = True
        await manager.send(self.project_id, TextBlockStart())

    async def on_text_delta(self, text: str) -> None:
        await manager.send(self.project_id, TextDelta(delta=text))

    async def on_text_end(self) -> None:
        if self._in_text_block:
            self._in_text_block = False
            await manager.send(self.project_id, TextBlockEnd())

    async def on_tool_start(self, tool_name: str) -> None:
        await manager.send(
            self.project_id,
            ToolActivity(tool_name=tool_name, status="started"),
        )

    async def on_tool_complete(self, tool_name: str, summary: str = "") -> None:
        await manager.send(
            self.project_id,
            ToolActivity(tool_name=tool_name, status="completed", result_summary=summary),
        )

    async def on_tool_error(self, tool_name: str, error: str) -> None:
        await manager.send(
            self.project_id,
            ToolActivity(tool_name=tool_name, status="error", result_summary=error),
        )
