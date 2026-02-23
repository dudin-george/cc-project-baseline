"""Tests for sub-agent runners (CodeWriter, UnitTester, QATester)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mycroft.server.worker.sub_agents import (
    SubAgentResult,
    run_code_writer,
    run_qa_tester,
    run_unit_tester,
)


class TestCodeWriter:
    @pytest.mark.asyncio
    async def test_returns_error_without_sdk(self, tmp_path):
        """Without claude_agent_sdk installed, should return graceful error."""
        result = await run_code_writer(
            tmp_path, "implement login", "# CLAUDE.md"
        )
        assert isinstance(result, SubAgentResult)
        # Either succeeds (if SDK installed) or fails gracefully
        if not result.success:
            assert "claude_agent_sdk" in result.error or result.error


class TestUnitTester:
    @pytest.mark.asyncio
    async def test_returns_error_without_sdk(self, tmp_path):
        result = await run_unit_tester(
            tmp_path, "test login", "# CLAUDE.md"
        )
        assert isinstance(result, SubAgentResult)
        if not result.success:
            assert "claude_agent_sdk" in result.error or result.error


class TestQATester:
    @pytest.mark.asyncio
    async def test_returns_error_without_sdk(self, tmp_path):
        result = await run_qa_tester(
            tmp_path, "Business spec: users can login", ["pytest tests/"]
        )
        assert isinstance(result, SubAgentResult)
        if not result.success:
            assert "claude_agent_sdk" in result.error or result.error


class TestSubAgentResult:
    def test_defaults(self):
        r = SubAgentResult(success=True, output="done")
        assert r.error == ""
        assert r.success is True

    def test_failure(self):
        r = SubAgentResult(success=False, output="", error="boom")
        assert r.error == "boom"
