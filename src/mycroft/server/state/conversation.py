"""Conversation JSONL persistence — one file per step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mycroft.shared.protocol import StepId
from mycroft.server.state.persistence import jsonl_append, jsonl_read


def _conv_path(project_dir: Path, step_id: StepId) -> Path:
    return project_dir / "conversations" / f"{step_id.value}.jsonl"


def append_message(project_dir: Path, step_id: StepId, message: dict[str, Any]) -> None:
    jsonl_append(_conv_path(project_dir, step_id), message)


def load_messages(project_dir: Path, step_id: StepId) -> list[dict[str, Any]]:
    return jsonl_read(_conv_path(project_dir, step_id))


def delete_conversation(project_dir: Path, step_id: StepId) -> None:
    path = _conv_path(project_dir, step_id)
    path.unlink(missing_ok=True)


def tail_messages(
    project_dir: Path, step_id: StepId, count: int = 20
) -> list[dict[str, Any]]:
    messages = load_messages(project_dir, step_id)
    return messages[-count:]
