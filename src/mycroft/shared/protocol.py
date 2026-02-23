"""WebSocket protocol message types for Mycroft client-server communication."""

from __future__ import annotations

import enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Enums ---


class StepId(str, enum.Enum):
    IDEA_SCOPING = "0"
    USE_CASES_MANUAL = "1.1"
    USE_CASES_AUTO = "1.2"
    ARCHITECTURE_MANUAL = "2.1"
    ARCHITECTURE_AUTO = "2.2"
    PROJECT_SETUP = "3.1"
    C4_DESIGN = "3.2"
    WORK_PLANNING = "4"
    EXECUTION = "5"
    E2E_TESTING = "6"


class StepStatus(str, enum.Enum):
    DRAFT = "draft"
    LOCKED = "locked"
    PERMANENTLY_LOCKED = "permanently_locked"


STEP_ORDER: list[StepId] = [
    StepId.IDEA_SCOPING,
    StepId.USE_CASES_MANUAL,
    StepId.USE_CASES_AUTO,
    StepId.ARCHITECTURE_MANUAL,
    StepId.ARCHITECTURE_AUTO,
    StepId.PROJECT_SETUP,
    StepId.C4_DESIGN,
    StepId.WORK_PLANNING,
    StepId.EXECUTION,
    StepId.E2E_TESTING,
]


# --- Client → Server messages ---


class AuthMessage(BaseModel):
    type: Literal["auth"] = "auth"
    api_key: str
    project_id: str | None = None  # None = new project


class UserMessage(BaseModel):
    type: Literal["message"] = "message"
    text: str


class CommandMessage(BaseModel):
    type: Literal["command"] = "command"
    name: str  # pause, next, back, status
    args: dict[str, Any] = Field(default_factory=dict)


class ConfirmResponse(BaseModel):
    type: Literal["confirm_response"] = "confirm_response"
    confirm_id: str
    approved: bool
    comment: str = ""


class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"


class WorkerCommand(BaseModel):
    type: Literal["worker_command"] = "worker_command"
    action: Literal[
        "pause_all", "resume_all", "retry", "cancel", "pause_service", "resume_service"
    ]
    task_id: str | None = None
    service_name: str | None = None


ClientMessage = (
    AuthMessage | UserMessage | CommandMessage | ConfirmResponse | PongMessage | WorkerCommand
)


def parse_client_message(data: dict[str, Any]) -> ClientMessage:
    type_map: dict[str, type[BaseModel]] = {
        "auth": AuthMessage,
        "message": UserMessage,
        "command": CommandMessage,
        "confirm_response": ConfirmResponse,
        "pong": PongMessage,
        "worker_command": WorkerCommand,
    }
    msg_type = data.get("type")
    if msg_type not in type_map:
        raise ValueError(f"Unknown client message type: {msg_type}")
    return type_map[msg_type].model_validate(data)


# --- Server → Client messages ---


class AuthResult(BaseModel):
    type: Literal["auth_result"] = "auth_result"
    success: bool
    project_id: str | None = None
    error: str | None = None


class StepState(BaseModel):
    step_id: StepId
    status: StepStatus


class StateSyncMessage(BaseModel):
    type: Literal["state_sync"] = "state_sync"
    project_id: str
    project_name: str
    current_step: StepId
    steps: list[StepState]
    conversation_tail: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirm: ConfirmRequest | None = None


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    delta: str


class TextBlockStart(BaseModel):
    type: Literal["text_block_start"] = "text_block_start"


class TextBlockEnd(BaseModel):
    type: Literal["text_block_end"] = "text_block_end"


class ToolActivity(BaseModel):
    type: Literal["tool_activity"] = "tool_activity"
    tool_name: str
    status: Literal["started", "completed", "error"]
    result_summary: str = ""


class ConfirmRequest(BaseModel):
    type: Literal["confirm_request"] = "confirm_request"
    confirm_id: str
    prompt: str
    context: str = ""


class TurnComplete(BaseModel):
    type: Literal["turn_complete"] = "turn_complete"


class StepTransition(BaseModel):
    type: Literal["step_transition"] = "step_transition"
    from_step: StepId | None = None
    to_step: StepId
    to_status: StepStatus


class PingMessage(BaseModel):
    type: Literal["ping"] = "ping"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True


class WorkerStatusUpdate(BaseModel):
    type: Literal["worker_status"] = "worker_status"
    task_id: str
    task_title: str
    service_name: str
    worker_id: str
    status: Literal["queued", "running", "pr_opened", "succeeded", "failed", "retrying"]
    pr_url: str | None = None
    error: str | None = None
    progress: str = ""


class WorkerBatchUpdate(BaseModel):
    type: Literal["worker_batch"] = "worker_batch"
    total_tasks: int
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    blocked: int = 0


class BlockerNotification(BaseModel):
    type: Literal["blocker_notification"] = "blocker_notification"
    blocker_id: str
    service_name: str
    question: str
    linear_issue_url: str = ""
    resolved: bool = False


ServerMessage = (
    AuthResult
    | StateSyncMessage
    | TextDelta
    | TextBlockStart
    | TextBlockEnd
    | ToolActivity
    | ConfirmRequest
    | TurnComplete
    | StepTransition
    | PingMessage
    | ErrorMessage
    | WorkerStatusUpdate
    | WorkerBatchUpdate
    | BlockerNotification
)


def parse_server_message(data: dict[str, Any]) -> ServerMessage:
    type_map: dict[str, type[BaseModel]] = {
        "auth_result": AuthResult,
        "state_sync": StateSyncMessage,
        "text_delta": TextDelta,
        "text_block_start": TextBlockStart,
        "text_block_end": TextBlockEnd,
        "tool_activity": ToolActivity,
        "confirm_request": ConfirmRequest,
        "turn_complete": TurnComplete,
        "step_transition": StepTransition,
        "ping": PingMessage,
        "error": ErrorMessage,
        "worker_status": WorkerStatusUpdate,
        "worker_batch": WorkerBatchUpdate,
        "blocker_notification": BlockerNotification,
    }
    msg_type = data.get("type")
    if msg_type not in type_map:
        raise ValueError(f"Unknown server message type: {msg_type}")
    return type_map[msg_type].model_validate(data)
