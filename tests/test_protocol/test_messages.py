"""Tests for WebSocket protocol message types."""

import pytest

from mycroft.shared.protocol import (
    AuthMessage,
    UserMessage,
    CommandMessage,
    ConfirmResponse,
    PongMessage,
    WorkerCommand,
    AuthResult,
    StateSyncMessage,
    TextDelta,
    ConfirmRequest,
    ErrorMessage,
    StepTransition,
    WorkerStatusUpdate,
    WorkerBatchUpdate,
    BlockerNotification,
    StepId,
    StepStatus,
    StepState,
    STEP_ORDER,
    parse_client_message,
    parse_server_message,
)


class TestStepOrder:
    def test_step_order_length(self):
        assert len(STEP_ORDER) == 10

    def test_step_order_values(self):
        assert STEP_ORDER[0] == StepId.IDEA_SCOPING
        assert STEP_ORDER[4] == StepId.ARCHITECTURE_AUTO
        assert STEP_ORDER[5] == StepId.PROJECT_SETUP
        assert STEP_ORDER[6] == StepId.C4_DESIGN
        assert STEP_ORDER[7] == StepId.WORK_PLANNING
        assert STEP_ORDER[8] == StepId.EXECUTION
        assert STEP_ORDER[-1] == StepId.E2E_TESTING


class TestParseClientMessage:
    def test_auth(self):
        msg = parse_client_message({"type": "auth", "api_key": "key123"})
        assert isinstance(msg, AuthMessage)
        assert msg.api_key == "key123"
        assert msg.project_id is None

    def test_auth_with_project(self):
        msg = parse_client_message(
            {"type": "auth", "api_key": "key", "project_id": "proj1"}
        )
        assert msg.project_id == "proj1"

    def test_message(self):
        msg = parse_client_message({"type": "message", "text": "hello"})
        assert isinstance(msg, UserMessage)
        assert msg.text == "hello"

    def test_command(self):
        msg = parse_client_message({"type": "command", "name": "next"})
        assert isinstance(msg, CommandMessage)
        assert msg.name == "next"
        assert msg.args == {}

    def test_command_with_args(self):
        msg = parse_client_message(
            {"type": "command", "name": "back", "args": {"target": "0"}}
        )
        assert msg.args == {"target": "0"}

    def test_confirm_response(self):
        msg = parse_client_message(
            {"type": "confirm_response", "confirm_id": "abc", "approved": True}
        )
        assert isinstance(msg, ConfirmResponse)
        assert msg.approved is True
        assert msg.comment == ""

    def test_confirm_response_with_comment(self):
        msg = parse_client_message(
            {
                "type": "confirm_response",
                "confirm_id": "abc",
                "approved": False,
                "comment": "nope",
            }
        )
        assert msg.approved is False
        assert msg.comment == "nope"

    def test_pong(self):
        msg = parse_client_message({"type": "pong"})
        assert isinstance(msg, PongMessage)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown client message type"):
            parse_client_message({"type": "bogus"})

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="Unknown client message type"):
            parse_client_message({"foo": "bar"})


class TestParseServerMessage:
    def test_auth_result_success(self):
        msg = parse_server_message(
            {"type": "auth_result", "success": True, "project_id": "p1"}
        )
        assert isinstance(msg, AuthResult)
        assert msg.success is True

    def test_auth_result_failure(self):
        msg = parse_server_message(
            {"type": "auth_result", "success": False, "error": "bad key"}
        )
        assert msg.error == "bad key"

    def test_text_delta(self):
        msg = parse_server_message({"type": "text_delta", "delta": "hello"})
        assert isinstance(msg, TextDelta)
        assert msg.delta == "hello"

    def test_confirm_request(self):
        msg = parse_server_message(
            {"type": "confirm_request", "confirm_id": "x", "prompt": "ok?"}
        )
        assert isinstance(msg, ConfirmRequest)
        assert msg.context == ""

    def test_error(self):
        msg = parse_server_message(
            {"type": "error", "message": "oops", "recoverable": False}
        )
        assert isinstance(msg, ErrorMessage)
        assert msg.recoverable is False

    def test_step_transition(self):
        msg = parse_server_message(
            {
                "type": "step_transition",
                "from_step": "0",
                "to_step": "1.1",
                "to_status": "draft",
            }
        )
        assert isinstance(msg, StepTransition)
        assert msg.from_step == StepId.IDEA_SCOPING
        assert msg.to_step == StepId.USE_CASES_MANUAL

    def test_state_sync(self):
        msg = parse_server_message(
            {
                "type": "state_sync",
                "project_id": "p1",
                "project_name": "test",
                "current_step": "0",
                "steps": [{"step_id": "0", "status": "draft"}],
            }
        )
        assert isinstance(msg, StateSyncMessage)
        assert msg.current_step == StepId.IDEA_SCOPING

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown server message type"):
            parse_server_message({"type": "bogus"})


class TestMessageRoundtrip:
    def test_auth_roundtrip(self):
        original = AuthMessage(api_key="key", project_id="p1")
        data = original.model_dump()
        parsed = parse_client_message(data)
        assert parsed == original

    def test_error_roundtrip(self):
        original = ErrorMessage(message="fail", recoverable=False)
        data = original.model_dump()
        parsed = parse_server_message(data)
        assert parsed == original


class TestWorkerCommand:
    def test_parse(self):
        msg = parse_client_message(
            {"type": "worker_command", "action": "pause_all"}
        )
        assert isinstance(msg, WorkerCommand)
        assert msg.action == "pause_all"
        assert msg.task_id is None
        assert msg.service_name is None

    def test_with_service(self):
        msg = parse_client_message(
            {"type": "worker_command", "action": "pause_service", "service_name": "auth"}
        )
        assert msg.service_name == "auth"

    def test_roundtrip(self):
        original = WorkerCommand(action="retry", task_id="t1")
        data = original.model_dump()
        parsed = parse_client_message(data)
        assert parsed == original


class TestWorkerStatusUpdate:
    def test_parse(self):
        msg = parse_server_message(
            {
                "type": "worker_status",
                "task_id": "t1",
                "task_title": "Login endpoint",
                "service_name": "auth",
                "worker_id": "w1",
                "status": "running",
            }
        )
        assert isinstance(msg, WorkerStatusUpdate)
        assert msg.status == "running"
        assert msg.pr_url is None
        assert msg.progress == ""

    def test_with_pr(self):
        msg = parse_server_message(
            {
                "type": "worker_status",
                "task_id": "t1",
                "task_title": "Login endpoint",
                "service_name": "auth",
                "worker_id": "w1",
                "status": "pr_opened",
                "pr_url": "https://github.com/org/repo/pull/1",
            }
        )
        assert msg.pr_url == "https://github.com/org/repo/pull/1"


class TestWorkerBatchUpdate:
    def test_parse(self):
        msg = parse_server_message(
            {
                "type": "worker_batch",
                "total_tasks": 10,
                "queued": 3,
                "running": 2,
                "succeeded": 4,
                "failed": 1,
            }
        )
        assert isinstance(msg, WorkerBatchUpdate)
        assert msg.total_tasks == 10
        assert msg.blocked == 0

    def test_roundtrip(self):
        original = WorkerBatchUpdate(total_tasks=5, running=2, succeeded=3)
        data = original.model_dump()
        parsed = parse_server_message(data)
        assert parsed == original


class TestBlockerNotification:
    def test_parse(self):
        msg = parse_server_message(
            {
                "type": "blocker_notification",
                "blocker_id": "b1",
                "service_name": "auth",
                "question": "Which OAuth provider?",
            }
        )
        assert isinstance(msg, BlockerNotification)
        assert msg.resolved is False
        assert msg.linear_issue_url == ""

    def test_resolved(self):
        msg = parse_server_message(
            {
                "type": "blocker_notification",
                "blocker_id": "b1",
                "service_name": "auth",
                "question": "Which OAuth provider?",
                "resolved": True,
                "linear_issue_url": "https://linear.app/issue/ABC-123",
            }
        )
        assert msg.resolved is True
