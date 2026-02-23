"""Tests for execution state persistence and crash recovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mycroft.server.worker.execution_state import (
    BlockerRecord,
    ExecutionState,
    ServiceRecord,
    SubAgentRecord,
    TaskRecord,
    TaskStatus,
    recover_execution,
)


@pytest.fixture()
def patch_data_dir(tmp_path, monkeypatch):
    """Patch settings.data_dir so projects_dir resolves to tmp_path/projects."""
    monkeypatch.setattr(
        "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
    )
    projects = tmp_path / "projects"
    projects.mkdir()
    return projects


@pytest.fixture()
def exec_state(patch_data_dir):
    """Create an ExecutionState with some tasks and services."""
    (patch_data_dir / "proj1").mkdir()

    state = ExecutionState(project_id="proj1")
    state.tasks = {
        "t1": TaskRecord(task_id="t1", title="User model", service_name="auth"),
        "t2": TaskRecord(task_id="t2", title="Login", service_name="auth"),
        "t3": TaskRecord(task_id="t3", title="Routes", service_name="api"),
    }
    state.services = {
        "auth": ServiceRecord(
            service_name="auth", task_ids=["t1", "t2"]
        ),
        "api": ServiceRecord(
            service_name="api", task_ids=["t3"]
        ),
    }
    state._recount()
    return state


class TestSaveLoadRoundTrip:
    def test_save_and_load(self, exec_state):
        exec_state.save()
        loaded = ExecutionState.load("proj1")

        assert loaded.project_id == "proj1"
        assert len(loaded.tasks) == 3
        assert len(loaded.services) == 2
        assert loaded.total_tasks == 3

    def test_exists(self, exec_state):
        assert not ExecutionState.exists("proj1")
        exec_state.save()
        assert ExecutionState.exists("proj1")

    def test_not_exists(self, patch_data_dir):
        assert not ExecutionState.exists("nonexistent")

    def test_round_trip_with_blockers(self, patch_data_dir):
        (patch_data_dir / "proj1").mkdir()

        state = ExecutionState(project_id="proj1")
        state.blockers["b1"] = BlockerRecord(
            blocker_id="b1",
            service_name="auth",
            question="Which provider?",
            linear_issue_id="lin-1",
        )
        state.save()

        loaded = ExecutionState.load("proj1")
        assert "b1" in loaded.blockers
        assert loaded.blockers["b1"].question == "Which provider?"
        assert not loaded.blockers["b1"].resolved


class TestCheckpointTaskStarted:
    def test_marks_in_progress(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        assert exec_state.tasks["t1"].status == TaskStatus.in_progress
        assert exec_state.tasks["t1"].attempts == 1
        assert exec_state.tasks["t1"].started_at != ""

    def test_increments_attempts(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        exec_state.checkpoint_task_started("t1")
        assert exec_state.tasks["t1"].attempts == 2

    def test_sets_service_current_task(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        assert exec_state.services["auth"].current_task_id == "t1"

    def test_nonexistent_task_is_noop(self, exec_state):
        exec_state.checkpoint_task_started("nonexistent")  # no error


class TestCheckpointTaskCompleted:
    def test_marks_succeeded(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        exec_state.checkpoint_task_completed("t1", success=True, pr_url="https://github.com/pr/1")

        assert exec_state.tasks["t1"].status == TaskStatus.succeeded
        assert exec_state.tasks["t1"].pr_url == "https://github.com/pr/1"
        assert exec_state.tasks["t1"].completed_at != ""
        assert "t1" in exec_state.services["auth"].completed_task_ids
        assert exec_state.succeeded == 1

    def test_marks_failed(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        exec_state.checkpoint_task_completed("t1", success=False, error="compile error")

        assert exec_state.tasks["t1"].status == TaskStatus.failed
        assert exec_state.tasks["t1"].error == "compile error"
        assert exec_state.failed == 1

    def test_stores_sub_agent_results(self, exec_state):
        records = [
            SubAgentRecord(agent_type="code_writer", success=True, output="done"),
            SubAgentRecord(agent_type="unit_tester", success=True, output="passed"),
        ]
        exec_state.checkpoint_task_completed("t1", success=True, sub_agent_results=records)

        assert len(exec_state.tasks["t1"].sub_agent_results) == 2
        assert exec_state.tasks["t1"].sub_agent_results[0].agent_type == "code_writer"

    def test_nonexistent_task_is_noop(self, exec_state):
        exec_state.checkpoint_task_completed("nonexistent", success=True)  # no error

    def test_persists_to_disk(self, exec_state, patch_data_dir):
        exec_state.checkpoint_task_completed("t1", success=True)

        # Verify file was written
        assert (patch_data_dir / "proj1" / "execution.json").exists()

        # Reload and verify
        loaded = ExecutionState.load("proj1")
        assert loaded.tasks["t1"].status == TaskStatus.succeeded


class TestCheckpointBlocker:
    def test_creates_blocker_record(self, exec_state):
        exec_state.checkpoint_blocker_created(
            "b1", "auth", "Which OAuth?", linear_issue_id="lin-1"
        )

        assert "b1" in exec_state.blockers
        assert exec_state.blockers["b1"].question == "Which OAuth?"
        assert not exec_state.blockers["b1"].resolved

    def test_resolves_blocker(self, exec_state):
        exec_state.checkpoint_blocker_created("b1", "auth", "question")
        exec_state.checkpoint_blocker_resolved("b1", "Use Google OAuth")

        assert exec_state.blockers["b1"].resolved
        assert exec_state.blockers["b1"].answer == "Use Google OAuth"

    def test_resolve_nonexistent_is_noop(self, exec_state):
        exec_state.checkpoint_blocker_resolved("nonexistent", "answer")  # no error


class TestGetPendingTaskIds:
    def test_returns_pending_tasks(self, exec_state):
        assert exec_state.get_pending_task_ids("auth") == ["t1", "t2"]
        assert exec_state.get_pending_task_ids("api") == ["t3"]

    def test_excludes_completed(self, exec_state):
        exec_state.checkpoint_task_completed("t1", success=True)
        assert exec_state.get_pending_task_ids("auth") == ["t2"]

    def test_excludes_in_progress(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        pending = exec_state.get_pending_task_ids("auth")
        assert "t1" not in pending

    def test_nonexistent_service(self, exec_state):
        assert exec_state.get_pending_task_ids("nonexistent") == []


class TestGetTasksNeedingRequeue:
    def test_finds_in_progress(self, exec_state):
        exec_state.checkpoint_task_started("t1")
        exec_state.checkpoint_task_started("t3")
        requeue = exec_state.get_tasks_needing_requeue()
        assert set(requeue) == {"t1", "t3"}

    def test_empty_when_none_in_progress(self, exec_state):
        assert exec_state.get_tasks_needing_requeue() == []


class TestRecount:
    def test_recount_consistency(self, exec_state):
        exec_state.checkpoint_task_completed("t1", success=True)
        exec_state.checkpoint_task_completed("t2", success=False)

        exec_state._recount()
        assert exec_state.succeeded == 1
        assert exec_state.failed == 1
        assert exec_state.pending == 1  # t3
        assert exec_state.total_tasks == 3


class TestRecovery:
    @pytest.mark.asyncio
    async def test_resets_in_progress_to_pending(self, patch_data_dir, monkeypatch):
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.linear_api_key", ""
        )
        (patch_data_dir / "proj1").mkdir()

        # Simulate crash: t1 succeeded, t2 in-progress, t3 pending
        state = ExecutionState(project_id="proj1")
        state.tasks = {
            "t1": TaskRecord(
                task_id="t1", title="Done", service_name="auth",
                status=TaskStatus.succeeded,
            ),
            "t2": TaskRecord(
                task_id="t2", title="Crashed", service_name="auth",
                status=TaskStatus.in_progress,
            ),
            "t3": TaskRecord(
                task_id="t3", title="Pending", service_name="api",
                status=TaskStatus.pending,
            ),
        }
        state.services = {
            "auth": ServiceRecord(
                service_name="auth",
                task_ids=["t1", "t2"],
                completed_task_ids=["t1"],
                current_task_id="t2",
            ),
            "api": ServiceRecord(
                service_name="api", task_ids=["t3"]
            ),
        }
        state._recount()
        state.save()

        recovered = await recover_execution("proj1")

        assert recovered.tasks["t1"].status == TaskStatus.succeeded
        assert recovered.tasks["t2"].status == TaskStatus.pending
        assert recovered.tasks["t3"].status == TaskStatus.pending
        assert recovered.services["auth"].current_task_id == ""
        assert recovered.succeeded == 1
        assert recovered.pending == 2

    @pytest.mark.asyncio
    async def test_reconciles_blockers_with_linear(self, patch_data_dir, monkeypatch):
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.linear_api_key", "test-key"
        )
        (patch_data_dir / "proj1").mkdir()

        state = ExecutionState(project_id="proj1")
        state.blockers = {
            "b1": BlockerRecord(
                blocker_id="b1",
                service_name="auth",
                question="Which provider?",
                linear_issue_id="lin-1",
            ),
        }
        state.save()

        mock_comment = AsyncMock()
        mock_comment.body = "Use Google OAuth"

        mock_lc = AsyncMock()
        mock_lc.get_issue_comments = AsyncMock(return_value=[mock_comment])

        with patch(
            "mycroft.server.linear.client.LinearClient",
            return_value=mock_lc,
        ):
            recovered = await recover_execution("proj1")

        assert recovered.blockers["b1"].resolved
        assert recovered.blockers["b1"].answer == "Use Google OAuth"

    @pytest.mark.asyncio
    async def test_all_tasks_completed(self, patch_data_dir, monkeypatch):
        """Recovery with all tasks done — nothing to resume."""
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.linear_api_key", ""
        )
        (patch_data_dir / "proj1").mkdir()

        state = ExecutionState(project_id="proj1")
        state.tasks = {
            "t1": TaskRecord(
                task_id="t1", title="Done", service_name="auth",
                status=TaskStatus.succeeded,
            ),
        }
        state.services = {
            "auth": ServiceRecord(
                service_name="auth",
                task_ids=["t1"],
                completed_task_ids=["t1"],
            ),
        }
        state._recount()
        state.save()

        recovered = await recover_execution("proj1")
        assert recovered.succeeded == 1
        assert recovered.pending == 0

    @pytest.mark.asyncio
    async def test_skips_linear_when_no_api_key(self, patch_data_dir, monkeypatch):
        """Recovery without Linear configured should still work."""
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.linear_api_key", ""
        )
        (patch_data_dir / "proj1").mkdir()

        state = ExecutionState(project_id="proj1")
        state.blockers = {
            "b1": BlockerRecord(
                blocker_id="b1",
                service_name="auth",
                question="question",
                linear_issue_id="lin-1",
            ),
        }
        state.save()

        recovered = await recover_execution("proj1")
        assert not recovered.blockers["b1"].resolved
