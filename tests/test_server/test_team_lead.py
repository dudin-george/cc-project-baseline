"""Tests for Team Lead task execution pipeline."""

from __future__ import annotations

import pytest

from mycroft.server.worker.execution_state import (
    ExecutionState,
    ServiceRecord,
    TaskRecord,
    TaskStatus,
)
from mycroft.server.worker.sub_agents import SubAgentResult
from mycroft.server.worker.team_lead import TaskResult, TeamLead, TeamLeadState


@pytest.fixture()
def team_lead(tmp_path, monkeypatch):
    """Create a team lead with mocked sub-agents."""
    lead = TeamLead(
        project_id="proj1",
        service_name="auth",
        repo_path=tmp_path,
        claude_md="# CLAUDE.md",
        business_spec="Users can login and register",
        tasks=[
            {"id": "t1", "title": "User model", "description": "Implement User model"},
            {"id": "t2", "title": "Login endpoint", "description": "Implement POST /login"},
        ],
    )
    return lead


class TestTeamLeadState:
    def test_initial_state(self, team_lead):
        assert team_lead.state.service_name == "auth"
        assert len(team_lead.state.tasks) == 2
        assert team_lead.state.current_task == ""
        assert not team_lead.state.paused

    def test_pause_resume(self, team_lead):
        team_lead.pause()
        assert team_lead.is_paused
        team_lead.resume()
        assert not team_lead.is_paused


class TestTeamLeadExecution:
    @pytest.mark.asyncio
    async def test_runs_all_tasks(self, team_lead, monkeypatch):
        """With mocked sub-agents, all tasks should complete."""
        _mock_all_sub_agents_success(monkeypatch)

        results = await team_lead.run()
        assert len(results) == 2
        assert all(r.success for r in results)
        assert team_lead.state.current_task == ""

    @pytest.mark.asyncio
    async def test_handles_failure_with_retry(self, team_lead, monkeypatch):
        """CodeWriter failure triggers retry."""
        call_count = {"n": 0}

        async def mock_code_writer(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:  # Fail first two calls (task 1 + retry)
                return SubAgentResult(success=False, output="", error="compile error")
            return SubAgentResult(success=True, output="done")

        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_code_writer", mock_code_writer
        )
        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_unit_tester", _mock_success
        )
        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_qa_tester", _mock_success
        )

        results = await team_lead.run()
        # Task 1 fails + 1 retry (still fails) = failed
        # Task 2 succeeds on first try
        assert len(results) == 2
        assert not results[0].success  # retried but still failed
        assert results[1].success

    @pytest.mark.asyncio
    async def test_cancel_stops_execution(self, team_lead, monkeypatch):
        _mock_all_sub_agents_success(monkeypatch)

        team_lead.cancel()
        results = await team_lead.run()
        assert len(results) == 0


class TestTaskResult:
    def test_success(self):
        r = TaskResult(task_id="t1", task_title="Test", success=True)
        assert r.success
        assert r.error == ""

    def test_failure(self):
        r = TaskResult(task_id="t1", task_title="Test", success=False, error="boom")
        assert not r.success
        assert r.error == "boom"


# ── Helpers ──────────────────────────────────────────────────


async def _mock_success(*args, **kwargs):
    return SubAgentResult(success=True, output="done")


def _mock_all_sub_agents_success(monkeypatch):
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_code_writer", _mock_success
    )
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_unit_tester", _mock_success
    )
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_qa_tester", _mock_success
    )


def _make_exec_state(tmp_path, monkeypatch):
    """Create an ExecutionState wired up for team lead tests."""
    monkeypatch.setattr(
        "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
    )
    (tmp_path / "projects" / "proj1").mkdir(parents=True, exist_ok=True)

    state = ExecutionState(project_id="proj1")
    state.tasks = {
        "t1": TaskRecord(task_id="t1", title="User model", service_name="auth"),
        "t2": TaskRecord(task_id="t2", title="Login endpoint", service_name="auth"),
    }
    state.services = {
        "auth": ServiceRecord(service_name="auth", task_ids=["t1", "t2"]),
    }
    state._recount()
    return state


class TestTeamLeadCheckpointing:
    @pytest.mark.asyncio
    async def test_checkpoints_on_success(self, tmp_path, monkeypatch):
        _mock_all_sub_agents_success(monkeypatch)
        exec_state = _make_exec_state(tmp_path, monkeypatch)

        lead = TeamLead(
            project_id="proj1",
            service_name="auth",
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
            tasks=[
                {"id": "t1", "title": "User model", "description": "impl"},
                {"id": "t2", "title": "Login endpoint", "description": "impl"},
            ],
            execution_state=exec_state,
        )

        results = await lead.run()
        assert len(results) == 2
        assert exec_state.tasks["t1"].status == TaskStatus.succeeded
        assert exec_state.tasks["t2"].status == TaskStatus.succeeded
        assert exec_state.succeeded == 2

    @pytest.mark.asyncio
    async def test_checkpoints_on_failure(self, tmp_path, monkeypatch):
        exec_state = _make_exec_state(tmp_path, monkeypatch)

        async def mock_code_writer_fail(*args, **kwargs):
            return SubAgentResult(success=False, output="", error="compile error")

        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_code_writer", mock_code_writer_fail
        )
        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_unit_tester", _mock_success
        )
        monkeypatch.setattr(
            "mycroft.server.worker.team_lead.run_qa_tester", _mock_success
        )

        lead = TeamLead(
            project_id="proj1",
            service_name="auth",
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
            tasks=[{"id": "t1", "title": "User model", "description": "impl"}],
            execution_state=exec_state,
        )

        results = await lead.run()
        assert not results[0].success
        assert exec_state.tasks["t1"].status == TaskStatus.failed
        assert exec_state.failed == 1

    @pytest.mark.asyncio
    async def test_no_checkpoint_without_exec_state(self, tmp_path, monkeypatch):
        """Team lead works normally without execution_state (backward compat)."""
        _mock_all_sub_agents_success(monkeypatch)

        lead = TeamLead(
            project_id="proj1",
            service_name="auth",
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
            tasks=[{"id": "t1", "title": "User model", "description": "impl"}],
        )
        assert lead.execution_state is None

        results = await lead.run()
        assert len(results) == 1
        assert results[0].success
