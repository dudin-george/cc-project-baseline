"""Tests for Team Lead task execution pipeline."""

from __future__ import annotations

import pytest

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
