"""CLI entry point for Mycroft client."""

from __future__ import annotations

import asyncio
import logging

import typer
from rich.console import Console

from mycroft.client.settings import client_settings
from mycroft.client.ws.client import MycroftClient
from mycroft.client.ui.renderer import Renderer
from mycroft.client.ui.input import AsyncInput
from mycroft.client.ui.commands import is_command, handle_command

logging.basicConfig(level=logging.WARNING)
console = Console()
app = typer.Typer(name="mycroft", help="Mycroft AI Product Development Pipeline")


async def _run_session(project_id: str | None = None) -> None:
    renderer = Renderer()

    async def on_message(msg):
        renderer.render_message(msg)

    client = MycroftClient(
        server_url=client_settings.server_url,
        api_key=client_settings.api_key,
        project_id=project_id,
        on_message=on_message,
    )

    async def on_input(text: str) -> None:
        # Handle confirm responses
        if renderer.pending_confirm:
            confirm = renderer.pending_confirm
            renderer.clear_pending_confirm()
            text_lower = text.lower().strip()
            if text_lower in ("y", "yes"):
                await client.send_confirm(confirm.confirm_id, True)
            elif text_lower in ("n", "no"):
                await client.send_confirm(confirm.confirm_id, False)
            else:
                # Treat as comment with approval
                await client.send_confirm(confirm.confirm_id, True, comment=text)
            return

        # Handle /commands
        if is_command(text):
            handled = await handle_command(client, text)
            if handled:
                return

        # Regular message
        await client.send_message(text)

    input_handler = AsyncInput(on_input=on_input)

    # Run connection and input concurrently
    connect_task = asyncio.create_task(client.connect())
    await client.wait_connected()

    input_task = asyncio.create_task(input_handler.run())

    try:
        done, pending = await asyncio.wait(
            [connect_task, input_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        input_handler.stop()
        await client.close()
        for task in [connect_task, input_task]:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


@app.command()
def new() -> None:
    """Start a new project."""
    console.print("[bold]Mycroft[/] - New Project")
    asyncio.run(_run_session(project_id=None))


@app.command()
def resume(project_id: str) -> None:
    """Resume an existing project."""
    console.print(f"[bold]Mycroft[/] - Resuming project [cyan]{project_id}[/]")
    asyncio.run(_run_session(project_id=project_id))


@app.command(name="list")
def list_projects() -> None:
    """List projects (requires server — shows local config only)."""
    console.print("[dim]Projects are stored on the server. Connect to see them.[/]")


if __name__ == "__main__":
    app()
