"""Tests for client command parsing."""

from unittest.mock import AsyncMock

import pytest

from mycroft.client.ui.commands import is_command, handle_command


class TestIsCommand:
    def test_valid_commands(self):
        assert is_command("/pause")
        assert is_command("/next")
        assert is_command("/back 0")
        assert is_command("/status")
        assert is_command("/name My Project")

    def test_unknown_command(self):
        assert not is_command("/unknown")

    def test_not_a_command(self):
        assert not is_command("hello")
        assert not is_command("pause")

    def test_slash_only(self):
        assert not is_command("/")

    def test_empty(self):
        assert not is_command("")


class TestHandleCommand:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.send_command = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_pause(self, mock_client):
        result = await handle_command(mock_client, "/pause")
        assert result is True
        mock_client.send_command.assert_called_once_with("pause")

    @pytest.mark.asyncio
    async def test_next(self, mock_client):
        result = await handle_command(mock_client, "/next")
        assert result is True
        mock_client.send_command.assert_called_once_with("next")

    @pytest.mark.asyncio
    async def test_status(self, mock_client):
        result = await handle_command(mock_client, "/status")
        assert result is True
        mock_client.send_command.assert_called_once_with("status")

    @pytest.mark.asyncio
    async def test_back_with_target(self, mock_client):
        result = await handle_command(mock_client, "/back 1.1")
        assert result is True
        mock_client.send_command.assert_called_once_with("back", {"target": "1.1"})

    @pytest.mark.asyncio
    async def test_back_without_target(self, mock_client):
        result = await handle_command(mock_client, "/back")
        assert result is True
        # Should print help, not call send_command
        mock_client.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_name_with_value(self, mock_client):
        result = await handle_command(mock_client, "/name My Cool App")
        assert result is True
        mock_client.send_command.assert_called_once_with("name", {"name": "My Cool App"})

    @pytest.mark.asyncio
    async def test_name_without_value(self, mock_client):
        result = await handle_command(mock_client, "/name")
        assert result is True
        mock_client.send_command.assert_not_called()
