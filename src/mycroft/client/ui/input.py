"""Async input handling with prompt_toolkit alongside WebSocket receive."""

from __future__ import annotations

from typing import Callable, Awaitable

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout


InputHandler = Callable[[str], Awaitable[None]]


class AsyncInput:
    def __init__(self, on_input: InputHandler) -> None:
        self.on_input = on_input
        self._session = PromptSession()
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                with patch_stdout():
                    text = await self._session.prompt_async("you> ")
                text = text.strip()
                if text:
                    await self.on_input(text)
            except EOFError:
                self._running = False
                break
            except KeyboardInterrupt:
                self._running = False
                break

    def stop(self) -> None:
        self._running = False
