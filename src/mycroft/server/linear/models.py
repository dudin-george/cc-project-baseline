"""Pydantic models for Linear API entities."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LinearProject(BaseModel):
    id: str
    name: str
    slug_id: str = ""
    url: str = ""


class LinearWorkflowState(BaseModel):
    id: str
    name: str
    type: str = ""  # e.g. "backlog", "unstarted", "started", "completed", "cancelled"


class LinearLabel(BaseModel):
    id: str
    name: str


class LinearComment(BaseModel):
    id: str
    body: str
    user_id: str = ""
    created_at: str = ""


class LinearIssue(BaseModel):
    id: str
    identifier: str = ""  # e.g. "ABC-123"
    title: str = ""
    description: str = ""
    state_id: str = ""
    priority: int = 0
    url: str = ""
    parent_id: str | None = None
    labels: list[LinearLabel] = Field(default_factory=list)


class LinearIssueCreateInput(BaseModel):
    title: str
    description: str = ""
    team_id: str = ""
    project_id: str | None = None
    parent_id: str | None = None
    state_id: str | None = None
    priority: int = 0
    label_ids: list[str] = Field(default_factory=list)
    assignee_id: str | None = None


class LinearIssueRelation(BaseModel):
    id: str
    issue_id: str
    related_issue_id: str
    type: str  # "blocks", "duplicate", "related"


class LinearWebhookPayload(BaseModel):
    action: str  # "create", "update", "remove"
    type: str  # "Issue", "Comment", etc.
    data: dict = Field(default_factory=dict)
    url: str = ""
    created_at: str = ""
    organization_id: str = ""
