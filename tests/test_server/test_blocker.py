"""Tests for the blocker lifecycle."""

from __future__ import annotations

import asyncio

import pytest

from mycroft.server.worker.blocker import (
    PendingBlocker,
    cleanup_blocker,
    clear_all_blockers,
    create_blocker,
    get_blocker,
    get_pending_blockers,
    resolve_blocker,
    resolve_blocker_by_linear_issue,
    restore_blockers_from_state,
)
from mycroft.server.worker.execution_state import (
    BlockerRecord,
    ExecutionState,
)


@pytest.fixture(autouse=True)
def _cleanup():
    clear_all_blockers()
    yield
    clear_all_blockers()


class TestCreateBlocker:
    @pytest.mark.asyncio
    async def test_creates_blocker(self, monkeypatch):
        # Disable Linear integration for unit test
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        # Mock manager.send to not require real WS
        monkeypatch.setattr(
            "mycroft.server.worker.blocker.manager.send",
            _mock_send,
        )

        blocker = await create_blocker("proj1", "auth", "Which OAuth provider?")
        assert isinstance(blocker, PendingBlocker)
        assert blocker.service_name == "auth"
        assert blocker.question == "Which OAuth provider?"
        assert not blocker.event.is_set()

    @pytest.mark.asyncio
    async def test_blocker_is_retrievable(self, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        blocker = await create_blocker("proj1", "auth", "question")
        assert get_blocker(blocker.blocker_id) is blocker

    @pytest.mark.asyncio
    async def test_multiple_blockers(self, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        b1 = await create_blocker("proj1", "auth", "q1")
        b2 = await create_blocker("proj1", "api", "q2")
        pending = get_pending_blockers()
        assert len(pending) == 2
        assert b1.blocker_id in pending
        assert b2.blocker_id in pending


class TestResolveBlocker:
    @pytest.mark.asyncio
    async def test_resolve_sets_event(self, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        blocker = await create_blocker("proj1", "auth", "which provider?")
        assert not blocker.event.is_set()

        result = resolve_blocker(blocker.blocker_id, "Use Google OAuth")
        assert result is True
        assert blocker.event.is_set()
        assert blocker.answer == "Use Google OAuth"

    def test_resolve_nonexistent_returns_false(self):
        assert resolve_blocker("nonexistent", "answer") is False

    @pytest.mark.asyncio
    async def test_resolve_by_linear_issue(self, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        blocker = await create_blocker("proj1", "auth", "question")
        blocker.linear_issue_id = "linear-123"

        result = resolve_blocker_by_linear_issue("linear-123", "the answer")
        assert result is True
        assert blocker.answer == "the answer"

    def test_resolve_by_linear_issue_not_found(self):
        assert resolve_blocker_by_linear_issue("missing", "answer") is False


class TestCleanupBlocker:
    @pytest.mark.asyncio
    async def test_cleanup(self, monkeypatch):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        blocker = await create_blocker("proj1", "auth", "q")
        assert get_blocker(blocker.blocker_id) is not None
        cleanup_blocker(blocker.blocker_id)
        assert get_blocker(blocker.blocker_id) is None


class TestBlockerWaitPattern:
    @pytest.mark.asyncio
    async def test_wait_and_resolve(self, monkeypatch):
        """Simulate the real pattern: create blocker, wait in background, resolve."""
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)

        blocker = await create_blocker("proj1", "auth", "question")

        async def _wait_for_answer():
            await blocker.event.wait()
            return blocker.answer

        async def _resolve_after_delay():
            await asyncio.sleep(0.01)
            resolve_blocker(blocker.blocker_id, "the answer")

        # Run both concurrently
        wait_task = asyncio.create_task(_wait_for_answer())
        resolve_task = asyncio.create_task(_resolve_after_delay())
        answer = await wait_task
        await resolve_task

        assert answer == "the answer"


# ── Helpers ──────────────────────────────────────────────────


async def _mock_send(*args, **kwargs):
    return True


class TestBlockerWithExecutionState:
    @pytest.mark.asyncio
    async def test_create_blocker_checkpoints(self, monkeypatch, tmp_path):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
        )
        (tmp_path / "projects" / "proj1").mkdir(parents=True)

        exec_state = ExecutionState(project_id="proj1")

        blocker = await create_blocker(
            "proj1", "auth", "Which provider?", execution_state=exec_state
        )

        assert blocker.blocker_id in exec_state.blockers
        assert exec_state.blockers[blocker.blocker_id].question == "Which provider?"
        assert not exec_state.blockers[blocker.blocker_id].resolved

    @pytest.mark.asyncio
    async def test_resolve_blocker_checkpoints(self, monkeypatch, tmp_path):
        monkeypatch.setattr("mycroft.server.worker.blocker.settings.linear_api_key", "")
        monkeypatch.setattr("mycroft.server.worker.blocker.manager.send", _mock_send)
        monkeypatch.setattr(
            "mycroft.server.worker.execution_state.settings.data_dir", tmp_path
        )
        (tmp_path / "projects" / "proj1").mkdir(parents=True)

        exec_state = ExecutionState(project_id="proj1")

        blocker = await create_blocker(
            "proj1", "auth", "Which provider?", execution_state=exec_state
        )
        resolve_blocker(blocker.blocker_id, "Use Google OAuth", execution_state=exec_state)

        assert exec_state.blockers[blocker.blocker_id].resolved
        assert exec_state.blockers[blocker.blocker_id].answer == "Use Google OAuth"


class TestRestoreBlockersFromState:
    def test_restores_unresolved(self):
        exec_state = ExecutionState(project_id="proj1")
        exec_state.blockers = {
            "b1": BlockerRecord(
                blocker_id="b1",
                service_name="auth",
                question="Which provider?",
                linear_issue_id="lin-1",
            ),
            "b2": BlockerRecord(
                blocker_id="b2",
                service_name="api",
                question="Which db?",
                resolved=True,
                answer="PostgreSQL",
            ),
        }

        restored = restore_blockers_from_state(exec_state)

        # Only b1 should be restored (b2 is already resolved)
        assert len(restored) == 1
        assert restored[0].blocker_id == "b1"
        assert restored[0].service_name == "auth"
        assert get_blocker("b1") is not None
        assert get_blocker("b2") is None  # resolved, not restored

    def test_restores_empty(self):
        exec_state = ExecutionState(project_id="proj1")
        restored = restore_blockers_from_state(exec_state)
        assert restored == []
