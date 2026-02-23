"""Sub-agent runners — spawn Claude Agent SDK instances for code/test/QA work.

Each sub-agent is a short-lived `query()` call with tailored context and tools.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mycroft.server.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    success: bool
    output: str
    error: str = ""


async def run_code_writer(
    worktree_path: Path,
    task_prompt: str,
    claude_md: str,
    max_turns: int | None = None,
) -> SubAgentResult:
    """Spawn a CodeWriter sub-agent to implement a task in a worktree.

    The CodeWriter receives:
    - Service spec + C4 L4 design (in task_prompt)
    - CLAUDE.md (project conventions)
    - Full file system access to the worktree
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query

        system = (
            "You are a CodeWriter agent. Implement the task described below precisely.\n"
            "Follow the C4 Level 4 design signatures exactly.\n"
            "Use shared utilities — never duplicate code.\n"
            "Run the linter before finishing.\n\n"
            f"## Project Instructions (CLAUDE.md)\n{claude_md}\n\n"
            f"## Working Directory\n{worktree_path}\n"
        )

        options = ClaudeAgentOptions(
            model=settings.claude_sdk_model,
            system_prompt=system,
            max_turns=max_turns or settings.worker_max_turns,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            working_directory=str(worktree_path),
        )

        result = await query(task_prompt, options=options)
        return SubAgentResult(success=True, output=result.text)

    except ImportError:
        logger.warning("claude_agent_sdk not installed, returning mock result")
        return SubAgentResult(
            success=False,
            output="",
            error="claude_agent_sdk not installed",
        )
    except Exception as e:
        logger.exception("CodeWriter failed")
        return SubAgentResult(success=False, output="", error=str(e))


async def run_unit_tester(
    worktree_path: Path,
    task_prompt: str,
    claude_md: str,
    max_turns: int | None = None,
) -> SubAgentResult:
    """Spawn a UnitTester sub-agent to write tests for implemented code.

    The UnitTester receives:
    - Implementation code context (in task_prompt)
    - Test patterns and conventions
    - File system access to the worktree
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query

        system = (
            "You are a UnitTester agent. Write comprehensive unit tests for the implementation.\n"
            "Test both happy paths and error cases.\n"
            "Mock external services — never call real APIs.\n"
            "Run the full test suite before finishing.\n\n"
            f"## Project Instructions (CLAUDE.md)\n{claude_md}\n\n"
            f"## Working Directory\n{worktree_path}\n"
        )

        options = ClaudeAgentOptions(
            model=settings.claude_sdk_model,
            system_prompt=system,
            max_turns=max_turns or settings.worker_max_turns,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            working_directory=str(worktree_path),
        )

        result = await query(task_prompt, options=options)
        return SubAgentResult(success=True, output=result.text)

    except ImportError:
        logger.warning("claude_agent_sdk not installed, returning mock result")
        return SubAgentResult(
            success=False,
            output="",
            error="claude_agent_sdk not installed",
        )
    except Exception as e:
        logger.exception("UnitTester failed")
        return SubAgentResult(success=False, output="", error=str(e))


async def run_qa_tester(
    worktree_path: Path,
    business_spec: str,
    test_commands: list[str],
    max_turns: int | None = None,
) -> SubAgentResult:
    """Spawn a QATester sub-agent for business-level validation.

    The QATester receives ONLY:
    - Business specs (use cases) — NO code or technical docs
    - Test commands to run
    - File system access (read-only intent, but can run tests)
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query

        system = (
            "You are a QATester agent. Validate the implementation against business specifications.\n"
            "You do NOT have access to code or technical architecture.\n"
            "Test from a USER perspective only.\n"
            "Report results in business language.\n\n"
            f"## Working Directory\n{worktree_path}\n"
        )

        prompt = (
            f"## Business Specifications\n{business_spec}\n\n"
            f"## Test Commands\nRun these to validate:\n"
        )
        for cmd in test_commands:
            prompt += f"- `{cmd}`\n"

        options = ClaudeAgentOptions(
            model=settings.claude_sdk_model,
            system_prompt=system,
            max_turns=max_turns or settings.worker_max_turns,
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            working_directory=str(worktree_path),
        )

        result = await query(prompt, options=options)
        return SubAgentResult(success=True, output=result.text)

    except ImportError:
        logger.warning("claude_agent_sdk not installed, returning mock result")
        return SubAgentResult(
            success=False,
            output="",
            error="claude_agent_sdk not installed",
        )
    except Exception as e:
        logger.exception("QATester failed")
        return SubAgentResult(success=False, output="", error=str(e))
