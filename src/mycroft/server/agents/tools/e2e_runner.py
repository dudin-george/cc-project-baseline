"""E2E test runner tool — run end-to-end tests in a project repository."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "run_e2e_tests",
    "description": (
        "Run end-to-end tests in the project repository. "
        "Executes a test command in the project's working directory and returns "
        "the output (stdout/stderr) and exit code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "Absolute path to the project repository.",
            },
            "test_command": {
                "type": "string",
                "description": (
                    "Shell command to run tests. Examples: "
                    "'pytest tests/ -v', 'npm test', 'make test'"
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum time to wait for tests to complete.",
                "default": 300,
            },
        },
        "required": ["repo_path", "test_command"],
    },
}


async def execute(project: ProjectState, input_data: dict[str, Any]) -> str:
    repo_path = Path(input_data["repo_path"])
    test_command = input_data["test_command"]
    timeout = input_data.get("timeout_seconds", 300)

    if not repo_path.exists():
        return json.dumps({
            "success": False,
            "exit_code": -1,
            "error": f"Repository path does not exist: {repo_path}",
        })

    logger.info("Running e2e tests in %s: %s", repo_path, test_command)

    try:
        process = await asyncio.create_subprocess_shell(
            test_command,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        exit_code = process.returncode or 0

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Truncate output if too long
        max_len = 10000
        if len(stdout_text) > max_len:
            stdout_text = stdout_text[:max_len] + "\n... (truncated)"
        if len(stderr_text) > max_len:
            stderr_text = stderr_text[:max_len] + "\n... (truncated)"

        return json.dumps({
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout_text,
            "stderr": stderr_text,
        })

    except asyncio.TimeoutError:
        return json.dumps({
            "success": False,
            "exit_code": -1,
            "error": f"Test command timed out after {timeout}s",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "exit_code": -1,
            "error": str(e),
        })
