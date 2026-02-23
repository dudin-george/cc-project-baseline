"""Tests for WebSocket connection manager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mycroft.server.ws.connection_manager import ConnectionManager
from mycroft.shared.protocol import ErrorMessage


@pytest.fixture
def mgr():
    return ConnectionManager()


def make_mock_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect(self, mgr):
        ws = make_mock_ws()
        await mgr.connect("p1", ws)
        assert mgr.is_connected("p1")

    @pytest.mark.asyncio
    async def test_replace_existing(self, mgr):
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await mgr.connect("p1", ws1)
        await mgr.connect("p1", ws2)
        ws1.close.assert_called_once()
        assert mgr.is_connected("p1")


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect(self, mgr):
        ws = make_mock_ws()
        await mgr.connect("p1", ws)
        await mgr.disconnect("p1")
        assert not mgr.is_connected("p1")

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent(self, mgr):
        # Should not raise
        await mgr.disconnect("nonexistent")


class TestSend:
    @pytest.mark.asyncio
    async def test_send_success(self, mgr):
        ws = make_mock_ws()
        await mgr.connect("p1", ws)
        msg = ErrorMessage(message="test")
        result = await mgr.send("p1", msg)
        assert result is True
        ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_connection(self, mgr):
        msg = ErrorMessage(message="test")
        result = await mgr.send("p1", msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_failure_disconnects(self, mgr):
        ws = make_mock_ws()
        ws.send_json.side_effect = RuntimeError("connection lost")
        await mgr.connect("p1", ws)
        msg = ErrorMessage(message="test")
        result = await mgr.send("p1", msg)
        assert result is False
        assert not mgr.is_connected("p1")


class TestIsConnected:
    @pytest.mark.asyncio
    async def test_not_connected(self, mgr):
        assert not mgr.is_connected("p1")

    @pytest.mark.asyncio
    async def test_connected(self, mgr):
        ws = make_mock_ws()
        await mgr.connect("p1", ws)
        assert mgr.is_connected("p1")
