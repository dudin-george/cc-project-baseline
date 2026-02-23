"""Tests for Orchestrator — Team Lead management and coordination."""

from __future__ import annotations

import pytest

from mycroft.server.worker.execution_state import (
    ExecutionState,
    ServiceRecord,
    TaskRecord,
    TaskStatus,
)
from mycroft.server.worker.orchestrator import Orchestrator
from mycroft.server.worker.sub_agents import SubAgentResult
from mycroft.server.worker.team_lead import TeamLead


@pytest.fixture()
def orchestrator(tmp_path, monkeypatch):
    """Create an orchestrator with 2 Team Leads and mocked sub-agents."""
    monkeypatch.setattr("mycroft.server.worker.orchestrator.manager.send", _mock_send)

    orch = Orchestrator("proj1")

    lead1 = TeamLead(
        project_id="proj1",
        service_name="auth",
        repo_path=tmp_path / "auth",
        claude_md="# CLAUDE.md",
        business_spec="Auth spec",
        tasks=[
            {"id": "t1", "title": "User model", "description": "impl"},
            {"id": "t2", "title": "Login", "description": "impl"},
        ],
    )
    lead2 = TeamLead(
        project_id="proj1",
        service_name="api",
        repo_path=tmp_path / "api",
        claude_md="# CLAUDE.md",
        business_spec="API spec",
        tasks=[
            {"id": "t3", "title": "Routes", "description": "impl"},
        ],
    )
    orch.add_team_lead(lead1)
    orch.add_team_lead(lead2)

    return orch


class TestOrchestratorSetup:
    def test_initial_state(self, orchestrator):
        assert orchestrator.state.total_tasks == 3
        assert orchestrator.state.queued == 3
        assert orchestrator.state.running == 0

    def test_get_status(self, orchestrator):
        status = orchestrator.get_status()
        assert status["total_tasks"] == 3
        assert "auth" in status["services"]
        assert "api" in status["services"]


class TestOrchestratorExecution:
    @pytest.mark.asyncio
    async def test_runs_all_services(self, orchestrator, monkeypatch):
        _mock_all_sub_agents(monkeypatch)

        await orchestrator.start()
        results = await orchestrator.wait()

        assert "auth" in results
        assert "api" in results
        assert len(results["auth"]) == 2
        assert len(results["api"]) == 1
        assert orchestrator.state.succeeded == 3

    @pytest.mark.asyncio
    async def test_pause_resume(self, orchestrator, monkeypatch):
        _mock_all_sub_agents(monkeypatch)

        orchestrator.pause_all()
        assert all(lead.is_paused for lead in orchestrator._leads.values())

        orchestrator.resume_all()
        assert all(not lead.is_paused for lead in orchestrator._leads.values())

    @pytest.mark.asyncio
    async def test_pause_single_service(self, orchestrator):
        assert orchestrator.pause_service("auth") is True
        assert orchestrator._leads["auth"].is_paused
        assert not orchestrator._leads["api"].is_paused

        assert orchestrator.resume_service("auth") is True
        assert not orchestrator._leads["auth"].is_paused

    def test_pause_nonexistent_service(self, orchestrator):
        assert orchestrator.pause_service("nonexistent") is False

    @pytest.mark.asyncio
    async def test_shutdown(self, orchestrator, monkeypatch):
        _mock_all_sub_agents(monkeypatch)

        await orchestrator.start()
        await orchestrator.shutdown()
        # After shutdown, all leads should be cancelled
        assert all(lead.state.cancelled for lead in orchestrator._leads.values())


# ── Helpers ──────────────────────────────────────────────────


async def _mock_send(*args, **kwargs):
    return True


async def _mock_success(*args, **kwargs):
    return SubAgentResult(success=True, output="done")


def _mock_all_sub_agents(monkeypatch):
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_code_writer", _mock_success
    )
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_unit_tester", _mock_success
    )
    monkeypatch.setattr(
        "mycroft.server.worker.team_lead.run_qa_tester", _mock_success
    )


class TestFromExecutionState:
    def test_rebuilds_with_pending_tasks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.orchestrator.manager.send", _mock_send)
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
        )
        (tmp_path / "projects" / "proj1").mkdir(parents=True)

        exec_state = ExecutionState(project_id="proj1")
        exec_state.tasks = {
            "t1": TaskRecord(
                task_id="t1", title="Done", service_name="auth",
                status=TaskStatus.succeeded,
            ),
            "t2": TaskRecord(
                task_id="t2", title="Pending", service_name="auth",
                status=TaskStatus.pending,
            ),
            "t3": TaskRecord(
                task_id="t3", title="Routes", service_name="api",
                status=TaskStatus.pending,
            ),
        }
        exec_state.services = {
            "auth": ServiceRecord(
                service_name="auth",
                task_ids=["t1", "t2"],
                completed_task_ids=["t1"],
            ),
            "api": ServiceRecord(
                service_name="api", task_ids=["t3"],
            ),
        }
        exec_state._recount()

        orch = Orchestrator.from_execution_state(
            exec_state,
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
        )

        assert "auth" in orch._leads
        assert "api" in orch._leads
        # auth lead only has 1 pending task (t2), t1 is done
        assert len(orch._leads["auth"].state.tasks) == 1
        assert orch._leads["auth"].state.tasks[0]["id"] == "t2"
        # api lead has 1 task
        assert len(orch._leads["api"].state.tasks) == 1
        # Counters
        assert orch.state.succeeded == 1
        assert orch.state.queued == 2  # t2 + t3
        assert orch.state.total_tasks == 3  # 1 done + 2 queued

    def test_skips_completed_services(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.orchestrator.manager.send", _mock_send)
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
        )
        (tmp_path / "projects" / "proj1").mkdir(parents=True)

        exec_state = ExecutionState(project_id="proj1")
        exec_state.tasks = {
            "t1": TaskRecord(
                task_id="t1", title="Done", service_name="auth",
                status=TaskStatus.succeeded,
            ),
        }
        exec_state.services = {
            "auth": ServiceRecord(
                service_name="auth",
                task_ids=["t1"],
                completed_task_ids=["t1"],
            ),
        }
        exec_state._recount()

        orch = Orchestrator.from_execution_state(
            exec_state,
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
        )

        # auth is fully complete — no Team Lead created
        assert "auth" not in orch._leads
        assert orch.state.succeeded == 1
        assert orch.state.queued == 0

    @pytest.mark.asyncio
    async def test_from_execution_state_runs(self, tmp_path, monkeypatch):
        """End-to-end: recover and run remaining tasks."""
        monkeypatch.setattr("mycroft.server.worker.orchestrator.manager.send", _mock_send)
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
        )
        (tmp_path / "projects" / "proj1").mkdir(parents=True)
        _mock_all_sub_agents(monkeypatch)

        exec_state = ExecutionState(project_id="proj1")
        exec_state.tasks = {
            "t1": TaskRecord(
                task_id="t1", title="Done", service_name="auth",
                status=TaskStatus.succeeded,
            ),
            "t2": TaskRecord(
                task_id="t2", title="Remaining", service_name="auth",
                status=TaskStatus.pending,
            ),
        }
        exec_state.services = {
            "auth": ServiceRecord(
                service_name="auth",
                task_ids=["t1", "t2"],
                completed_task_ids=["t1"],
            ),
        }
        exec_state._recount()

        orch = Orchestrator.from_execution_state(
            exec_state,
            repo_path=tmp_path,
            claude_md="# CLAUDE.md",
            business_spec="spec",
        )

        await orch.start()
        results = await orch.wait()

        assert "auth" in results
        assert len(results["auth"]) == 1
        assert results["auth"][0].success
