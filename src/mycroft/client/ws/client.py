"""WebSocket client with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from mycroft.shared.protocol import AuthMessage, parse_server_message, ServerMessage

logger = logging.getLogger(__name__)

MessageHandler = Callable[[ServerMessage], Awaitable[None]]


class MycroftClient:
    def __init__(
        self,
        server_url: str,
        api_key: str,
        project_id: str | None = None,
        on_message: MessageHandler | None = None,
    ) -> None:
        self.server_url = server_url
        self.api_key = api_key
        self.project_id = project_id
        self.on_message = on_message
        self._ws: ClientConnection | None = None
        self._connected = asyncio.Event()
        self._closed = False
        self._reconnect_delay = 1.0

    async def connect(self) -> None:
        self._closed = False
        while not self._closed:
            try:
                self._ws = await websockets.connect(self.server_url)
                self._reconnect_delay = 1.0

                # Authenticate
                auth = AuthMessage(api_key=self.api_key, project_id=self.project_id)
                await self._ws.send(json.dumps(auth.model_dump()))

                self._connected.set()
                logger.info("Connected to server")

                # Receive loop
                async for raw in self._ws:
                    data = json.loads(raw)
                    msg = parse_server_message(data)

                    # Track project_id from auth_result
                    if msg.type == "auth_result" and msg.success and msg.project_id:
                        self.project_id = msg.project_id

                    # Handle pings
                    if msg.type == "ping":
                        await self.send_raw({"type": "pong"})
                        continue

                    if self.on_message:
                        await self.on_message(msg)

            except websockets.ConnectionClosed:
                logger.info("Connection closed")
                self._connected.clear()
                if self._closed:
                    break
            except (OSError, websockets.InvalidURI) as e:
                logger.warning("Connection failed: %s", e)
                self._connected.clear()

            if not self._closed:
                logger.info("Reconnecting in %.1fs...", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)

    async def send_raw(self, data: dict[str, Any]) -> None:
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_message(self, text: str) -> None:
        await self.send_raw({"type": "message", "text": text})

    async def send_command(self, name: str, args: dict[str, Any] | None = None) -> None:
        await self.send_raw({"type": "command", "name": name, "args": args or {}})

    async def send_confirm(self, confirm_id: str, approved: bool, comment: str = "") -> None:
        await self.send_raw({
            "type": "confirm_response",
            "confirm_id": confirm_id,
            "approved": approved,
            "comment": comment,
        })

    async def wait_connected(self) -> None:
        await self._connected.wait()

    async def close(self) -> None:
        self._closed = True
        self._connected.clear()
        if self._ws:
            await self._ws.close()
