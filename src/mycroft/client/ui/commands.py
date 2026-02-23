"""Parse and handle client-side /commands."""

from __future__ import annotations

from mycroft.client.ws.client import MycroftClient


COMMANDS = {"/pause", "/next", "/back", "/status", "/name"}


def is_command(text: str) -> bool:
    return text.startswith("/") and text.split()[0] in COMMANDS


async def handle_command(client: MycroftClient, text: str) -> bool:
    """Handle a /command. Returns True if handled."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "/pause":
        await client.send_command("pause")
        return True

    if cmd == "/next":
        await client.send_command("next")
        return True

    if cmd == "/back":
        if not rest:
            from rich.console import Console
            Console().print("[yellow]Usage: /back <step_id> (e.g. /back 0, /back 1.1)[/]")
            return True
        await client.send_command("back", {"target": rest.strip()})
        return True

    if cmd == "/status":
        await client.send_command("status")
        return True

    if cmd == "/name":
        if not rest:
            from rich.console import Console
            Console().print("[yellow]Usage: /name <project name>[/]")
            return True
        await client.send_command("name", {"name": rest.strip()})
        return True

    return False
