"""Rich-based UI rendering for agent messages, panels, and spinners."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel

from mycroft.shared.protocol import (
    ServerMessage,
    StateSyncMessage,
    StepId,
    StepStatus,
    StepTransition,
    ErrorMessage,
    ConfirmRequest,
    ToolActivity,
    TurnComplete,
)

console = Console()

STEP_NAMES: dict[StepId, str] = {
    StepId.IDEA_SCOPING: "Step 0: Idea Scoping",
    StepId.USE_CASES_MANUAL: "Step 1.1: Manual Use Cases",
    StepId.USE_CASES_AUTO: "Step 1.2: Auto Use Cases",
    StepId.ARCHITECTURE_MANUAL: "Step 2.1: Manual Architecture",
    StepId.ARCHITECTURE_AUTO: "Step 2.2: Auto Architecture",
}

STATUS_ICONS: dict[StepStatus, str] = {
    StepStatus.DRAFT: "[yellow]draft[/]",
    StepStatus.LOCKED: "[green]locked[/]",
    StepStatus.PERMANENTLY_LOCKED: "[red]permanently locked[/]",
}


class Renderer:
    def __init__(self) -> None:
        self._streaming = False
        self._stream_buffer = ""
        self._pending_confirm: ConfirmRequest | None = None

    def render_message(self, msg: ServerMessage) -> None:
        handler = getattr(self, f"_render_{msg.type}", None)
        if handler:
            handler(msg)

    def _render_auth_result(self, msg: Any) -> None:
        if msg.success:
            console.print(f"[green]Connected[/] to project [bold]{msg.project_id}[/]")
        else:
            console.print(f"[red]Auth failed:[/] {msg.error}")

    def _render_state_sync(self, msg: StateSyncMessage) -> None:
        console.print()
        console.print(
            Panel(
                self._format_pipeline_status(msg),
                title=f"[bold]{msg.project_name}[/]",
                border_style="blue",
            )
        )
        if msg.conversation_tail:
            console.print("[dim]--- Recent conversation ---[/]")
            for m in msg.conversation_tail:
                role = m.get("role", "?")
                content = m.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if b.get("type") == "text"
                    )
                prefix = "[bold cyan]You:[/]" if role == "user" else "[bold green]Agent:[/]"
                console.print(f"  {prefix} {content[:200]}")

        if msg.pending_confirm:
            self._render_confirm_request(msg.pending_confirm)

        console.print()

    def _format_pipeline_status(self, msg: StateSyncMessage) -> str:
        lines = []
        for step in msg.steps:
            name = STEP_NAMES.get(step.step_id, step.step_id.value)
            icon = STATUS_ICONS.get(step.status, str(step.status))
            marker = " <--" if step.step_id == msg.current_step else ""
            lines.append(f"  {name}: {icon}{marker}")
        return "\n".join(lines)

    def _render_text_block_start(self, msg: Any) -> None:
        self._streaming = True
        self._stream_buffer = ""

    def _render_text_delta(self, msg: Any) -> None:
        sys.stdout.write(msg.delta)
        sys.stdout.flush()
        self._stream_buffer += msg.delta

    def _render_text_block_end(self, msg: Any) -> None:
        if self._streaming:
            sys.stdout.write("\n")
            sys.stdout.flush()
        self._streaming = False
        self._stream_buffer = ""

    def _render_tool_activity(self, msg: ToolActivity) -> None:
        if msg.status == "started":
            console.print(f"  [dim]using {msg.tool_name}...[/]")
        elif msg.status == "completed":
            summary = f": {msg.result_summary}" if msg.result_summary else ""
            console.print(f"  [dim]{msg.tool_name} done{summary}[/]")
        elif msg.status == "error":
            console.print(f"  [red]{msg.tool_name} error: {msg.result_summary}[/]")

    def _render_confirm_request(self, msg: ConfirmRequest) -> None:
        self._pending_confirm = msg
        console.print()
        console.print(
            Panel(
                msg.prompt + (f"\n\n[dim]{msg.context}[/]" if msg.context else ""),
                title="[bold yellow]Agent needs your input[/]",
                border_style="yellow",
            )
        )
        console.print("[yellow]Type 'y' to approve, 'n' to reject, or add a comment:[/]")

    def _render_turn_complete(self, msg: TurnComplete) -> None:
        pass  # input prompt will appear naturally

    def _render_step_transition(self, msg: StepTransition) -> None:
        from_str = STEP_NAMES.get(msg.from_step, "?") if msg.from_step else "start"
        to_str = STEP_NAMES.get(msg.to_step, msg.to_step.value)
        console.print(f"\n[bold blue]Pipeline: {from_str} -> {to_str}[/]\n")

    def _render_error(self, msg: ErrorMessage) -> None:
        console.print(f"\n[red]Error: {msg.message}[/]")

    def _render_ping(self, msg: Any) -> None:
        pass

    @property
    def pending_confirm(self) -> ConfirmRequest | None:
        return self._pending_confirm

    def clear_pending_confirm(self) -> None:
        self._pending_confirm = None
