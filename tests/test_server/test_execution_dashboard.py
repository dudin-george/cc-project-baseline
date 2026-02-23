"""Tests for execution dashboard agent — registry, commands, Linear population."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mycroft.server.agents.execution_dashboard import (
    ExecutionDashboardAgent,
    _orchestrators,
    clear_orchestrators,
    extract_service_name,
    get_orchestrator,
)
from mycroft.server.worker.execution_state import ExecutionState, ServiceRecord, TaskRecord
from mycroft.server.worker.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _cleanup():
    clear_orchestrators()
    yield
    clear_orchestrators()


# ── Service name extraction ───────────────────────────────────


class TestExtractServiceName:
    def test_bracket_pattern(self):
        assert extract_service_name("[Auth] Service setup") == "auth"

    def test_bracket_with_spaces(self):
        assert extract_service_name("[ Payment Gateway ] Integration") == "payment gateway"

    def test_no_brackets(self):
        assert extract_service_name("Some plain title") == "some plain title"

    def test_empty_brackets(self):
        # Regex won't match empty brackets — falls through to full title
        assert extract_service_name("[] Something") == "[] something"


# ── Orchestrator registry ─────────────────────────────────────


class TestOrchestratorRegistry:
    def test_get_returns_none_when_empty(self):
        assert get_orchestrator("p1") is None

    def test_store_and_get(self):
        orch = Orchestrator("p1")
        _orchestrators["p1"] = orch
        assert get_orchestrator("p1") is orch

    def test_clear(self):
        _orchestrators["p1"] = Orchestrator("p1")
        _orchestrators["p2"] = Orchestrator("p2")
        clear_orchestrators()
        assert get_orchestrator("p1") is None
        assert get_orchestrator("p2") is None


# ── Dashboard command handlers ────────────────────────────────


def _make_agent() -> ExecutionDashboardAgent:
    """Create a dashboard agent with a mock project."""
    project = MagicMock()
    project.project_id = "test-proj"
    project.metadata = {}
    agent = ExecutionDashboardAgent(project)
    return agent


class TestDashboardPause:
    @pytest.mark.asyncio
    async def test_pause_calls_orchestrator(self):
        agent = _make_agent()
        orch = MagicMock(spec=Orchestrator)
        orch.state = MagicMock(total_tasks=5, queued=2, running=1, succeeded=1, failed=0, blocked=1)
        _orchestrators["test-proj"] = orch

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_pause()

        orch.pause_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_no_orchestrator(self):
        agent = _make_agent()

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_pause()

        # Should send error message
        mock_manager.send.assert_called_once()
        call_args = mock_manager.send.call_args
        assert call_args[0][0] == "test-proj"
        assert "No active execution" in call_args[0][1].message


class TestDashboardResume:
    @pytest.mark.asyncio
    async def test_resume_calls_orchestrator(self):
        agent = _make_agent()
        orch = MagicMock(spec=Orchestrator)
        orch.state = MagicMock(total_tasks=5, queued=2, running=1, succeeded=1, failed=0, blocked=1)
        _orchestrators["test-proj"] = orch

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_resume()

        orch.resume_all.assert_called_once()


class TestDashboardStatus:
    @pytest.mark.asyncio
    async def test_status_sends_data(self):
        agent = _make_agent()
        orch = MagicMock(spec=Orchestrator)
        orch.get_status.return_value = {
            "total_tasks": 10,
            "queued": 3,
            "running": 2,
            "succeeded": 4,
            "failed": 1,
            "blocked": 0,
            "services": {},
        }
        _orchestrators["test-proj"] = orch

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send_json = AsyncMock()
            await agent._handle_status()

        mock_manager.send_json.assert_called_once()
        call_args = mock_manager.send_json.call_args
        assert call_args[0][0] == "test-proj"
        data = call_args[0][1]
        assert data["type"] == "execution_status"
        assert data["total_tasks"] == 10

    @pytest.mark.asyncio
    async def test_status_no_orchestrator(self):
        agent = _make_agent()

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_status()

        mock_manager.send.assert_called_once()
        assert "No active execution" in mock_manager.send.call_args[0][1].message


class TestDashboardRetry:
    @pytest.mark.asyncio
    async def test_retry_resumes_service(self):
        agent = _make_agent()
        orch = MagicMock(spec=Orchestrator)
        orch.resume_service.return_value = True
        orch.state = MagicMock(total_tasks=5, queued=2, running=1, succeeded=1, failed=0, blocked=1)
        _orchestrators["test-proj"] = orch

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_retry("auth")

        orch.resume_service.assert_called_once_with("auth")

    @pytest.mark.asyncio
    async def test_retry_unknown_service(self):
        agent = _make_agent()
        orch = MagicMock(spec=Orchestrator)
        orch.resume_service.return_value = False
        _orchestrators["test-proj"] = orch

        with patch("mycroft.server.agents.execution_dashboard.manager") as mock_manager:
            mock_manager.send = AsyncMock()
            await agent._handle_retry("nonexistent")

        assert "not found" in mock_manager.send.call_args[0][1].message


# ── Linear population ─────────────────────────────────────────


class TestPopulateFromLinear:
    @pytest.mark.asyncio
    async def test_populates_services_and_tasks(self):
        agent = _make_agent()
        agent.project.metadata = {"linear_project_id": "lp1"}

        from mycroft.server.linear.models import LinearIssue

        mock_issues = [
            # Story 1 (no parent)
            LinearIssue(id="s1", identifier="ABC-1", title="[Auth] Authentication Service"),
            # Story 2
            LinearIssue(id="s2", identifier="ABC-2", title="[Payments] Payment Service"),
            # Tasks under story 1
            LinearIssue(id="t1", identifier="ABC-3", title="Implement login", parent_id="s1"),
            LinearIssue(id="t2", identifier="ABC-4", title="Add JWT validation", parent_id="s1"),
            # Task under story 2
            LinearIssue(id="t3", identifier="ABC-5", title="Stripe integration", parent_id="s2"),
        ]

        mock_client = AsyncMock()
        mock_client.list_project_issues.return_value = mock_issues
        mock_client.close = AsyncMock()

        exec_state = ExecutionState(project_id="test-proj")

        with patch("mycroft.server.agents.execution_dashboard.LinearClient", return_value=mock_client), \
             patch("mycroft.server.agents.execution_dashboard.server_settings") as mock_settings:
            mock_settings.linear_api_key = "key"
            await agent._populate_from_linear(exec_state)

        # Should have 2 services
        assert len(exec_state.services) == 2
        assert "auth" in exec_state.services
        assert "payments" in exec_state.services

        # Should have 3 tasks
        assert len(exec_state.tasks) == 3
        assert exec_state.tasks["t1"].service_name == "auth"
        assert exec_state.tasks["t2"].service_name == "auth"
        assert exec_state.tasks["t3"].service_name == "payments"

        # Service task_ids should be correct
        assert exec_state.services["auth"].task_ids == ["t1", "t2"]
        assert exec_state.services["payments"].task_ids == ["t3"]

        # Counters should be recomputed
        assert exec_state.total_tasks == 3
        assert exec_state.pending == 3

    @pytest.mark.asyncio
    async def test_no_linear_project_id(self):
        agent = _make_agent()
        agent.project.metadata = {}

        exec_state = ExecutionState(project_id="test-proj")
        await agent._populate_from_linear(exec_state)

        assert len(exec_state.tasks) == 0
        assert len(exec_state.services) == 0

    @pytest.mark.asyncio
    async def test_linear_error_graceful(self):
        agent = _make_agent()
        agent.project.metadata = {"linear_project_id": "lp1"}

        exec_state = ExecutionState(project_id="test-proj")

        with patch("mycroft.server.agents.execution_dashboard.LinearClient", side_effect=Exception("boom")), \
             patch("mycroft.server.agents.execution_dashboard.server_settings") as mock_settings:
            mock_settings.linear_api_key = "key"
            await agent._populate_from_linear(exec_state)

        # Should not crash, just return empty
        assert len(exec_state.tasks) == 0


# ── Run command routing ───────────────────────────────────────


class TestRunRouting:
    @pytest.mark.asyncio
    async def test_start_routes_to_handle_start(self):
        agent = _make_agent()
        agent._handle_start = AsyncMock()
        await agent.run("start")
        agent._handle_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_routes_to_handle_pause(self):
        agent = _make_agent()
        agent._handle_pause = AsyncMock()
        await agent.run("pause")
        agent._handle_pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_routes_to_handle_resume(self):
        agent = _make_agent()
        agent._handle_resume = AsyncMock()
        await agent.run("resume")
        agent._handle_resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_routes_to_handle_status(self):
        agent = _make_agent()
        agent._handle_status = AsyncMock()
        await agent.run("status")
        agent._handle_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_routes_to_handle_retry(self):
        agent = _make_agent()
        agent._handle_retry = AsyncMock()
        await agent.run("retry auth-service")
        agent._handle_retry.assert_called_once_with("auth-service")
