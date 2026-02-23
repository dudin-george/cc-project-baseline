"""Atomic file I/O for state persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(tmp_fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        Path(tmp_path).replace(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def json_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def jsonl_append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records
