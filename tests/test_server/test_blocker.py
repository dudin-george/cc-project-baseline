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
