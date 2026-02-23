"""ProjectState: per-project persistent state."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mycroft.server.settings import settings
from mycroft.shared.protocol import StepId, StepStatus, STEP_ORDER
from mycroft.server.state.persistence import atomic_json_write, json_read


class StepState(BaseModel):
    step_id: StepId
    status: StepStatus = StepStatus.DRAFT


class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    project_name: str = "untitled"
    current_step: StepId = StepId.IDEA_SCOPING
    steps: dict[StepId, StepState] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        for sid in STEP_ORDER:
            if sid not in self.steps:
                self.steps[sid] = StepState(step_id=sid)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.project_name.lower()).strip("-") or self.project_id

    @property
    def project_dir(self) -> Path:
        return settings.projects_dir / self.project_id

    def save(self) -> None:
        path = self.project_dir / "state.json"
        atomic_json_write(path, self.model_dump())

    @classmethod
    def load(cls, project_id: str) -> ProjectState:
        path = settings.projects_dir / project_id / "state.json"
        data = json_read(path)
        return cls.model_validate(data)

    @classmethod
    def exists(cls, project_id: str) -> bool:
        return (settings.projects_dir / project_id / "state.json").exists()

    @classmethod
    def list_all(cls) -> list[ProjectState]:
        projects = []
        projects_dir = settings.projects_dir
        if not projects_dir.exists():
            return projects
        for d in projects_dir.iterdir():
            if d.is_dir() and (d / "state.json").exists():
                projects.append(cls.load(d.name))
        return projects
