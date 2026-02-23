"""Tests for user_confirm tool: pending state, resolve, reconnect."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mycroft.server.agents.tools.user_confirm import (
    execute,
    resolve_confirm,
    get_pending_confirm,
    _pending,
)


@pytest.fixture(autouse=True)
def clear_pending():
    _pending.clear()
    yield
    _pending.clear()


class TestGetPendingConfirm:
    def test_no_pending(self):
        assert get_pending_confirm("proj1") is None

    def test_returns_pending(self):
        from mycroft.server.agents.tools.user_confirm import PendingConfirm

        pc = PendingConfirm("abc", "approve?", "some context")
        _pending["proj1"] = pc
        result = get_pending_confirm("proj1")
        assert result is not None
        assert result.confirm_id == "abc"
        assert result.prompt == "approve?"
        assert result.context == "some context"


class TestResolveConfirm:
    def test_resolve_valid(self):
        from mycroft.server.agents.tools.user_confirm import PendingConfirm

        pc = PendingConfirm("abc", "ok?", "")
        _pending["proj1"] = pc
        resolve_confirm("proj1", "abc", True, "looks good")
        assert pc.approved is True
        assert pc.comment == "looks good"
        assert pc.event.is_set()

    def test_resolve_mismatched_id(self):
        from mycroft.server.agents.tools.user_confirm import PendingConfirm

        pc = PendingConfirm("abc", "ok?", "")
        _pending["proj1"] = pc
        resolve_confirm("proj1", "wrong_id", True, "")
        assert not pc.event.is_set()

    def test_resolve_nonexistent_project(self):
        # Should not raise
        resolve_confirm("nonexistent", "abc", True, "")


class TestExecuteAndResolve:
    @pytest.mark.asyncio
    async def test_execute_blocks_until_resolved(self):
        with patch("mycroft.server.agents.tools.user_confirm.manager") as mock_mgr:
            mock_mgr.send = AsyncMock(return_value=True)

            async def resolve_after_delay():
                await asyncio.sleep(0.05)
                # Find the pending confirm and resolve it
                pc = _pending.get("proj1")
                assert pc is not None
                resolve_confirm("proj1", pc.confirm_id, True, "yes")

            task = asyncio.create_task(
                execute("proj1", {"prompt": "approve this?"})
            )
            resolver = asyncio.create_task(resolve_after_delay())

            result = await task
            await resolver

            import json

            data = json.loads(result)
            assert data["approved"] is True
            assert data["comment"] == "yes"

        # Pending should be cleaned up
        assert "proj1" not in _pending

    @pytest.mark.asyncio
    async def test_execute_sends_confirm_request(self):
        with patch("mycroft.server.agents.tools.user_confirm.manager") as mock_mgr:
            mock_mgr.send = AsyncMock(return_value=True)

            async def resolve_quickly():
                await asyncio.sleep(0.05)
                pc = _pending.get("proj1")
                if pc:
                    resolve_confirm("proj1", pc.confirm_id, False, "nah")

            task = asyncio.create_task(
                execute("proj1", {"prompt": "check?", "context": "ctx"})
            )
            resolver = asyncio.create_task(resolve_quickly())

            await task
            await resolver

            mock_mgr.send.assert_called_once()
            call_args = mock_mgr.send.call_args
            assert call_args[0][0] == "proj1"
            msg = call_args[0][1]
            assert msg.prompt == "check?"
            assert msg.context == "ctx"
