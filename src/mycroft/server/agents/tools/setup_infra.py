"""Setup infrastructure tool — create GitHub repo from template + Linear project."""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.server.git.github import GitHubClient
from mycroft.server.git.template import populate_repo, write_claude_md
from mycroft.server.linear.client import LinearClient
from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "setup_infra",
    "description": (
        "Create a GitHub repository from the project template and a Linear project "
        "for task management. This sets up the complete infrastructure for execution. "
        "Call this once during the Project Setup step."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo_name": {
                "type": "string",
                "description": "Name for the new GitHub repository (e.g. 'taskflow-app').",
            },
            "repo_description": {
                "type": "string",
                "description": "Short description for the GitHub repo.",
                "default": "",
            },
            "linear_project_name": {
                "type": "string",
                "description": "Name for the Linear project (e.g. 'TaskFlow v1.0').",
            },
            "private": {
                "type": "boolean",
                "description": "Whether the GitHub repo should be private.",
                "default": True,
            },
        },
        "required": ["repo_name", "linear_project_name"],
    },
}


async def execute(project: ProjectState, input_data: dict[str, Any]) -> str:
    repo_name = input_data["repo_name"]
    repo_desc = input_data.get("repo_description", "")
    linear_name = input_data["linear_project_name"]
    private = input_data.get("private", True)

    result: dict[str, Any] = {"repo_created": False, "linear_project_created": False}

    # Create GitHub repo from template
    if settings.github_token and settings.template_repo:
        try:
            gh = GitHubClient()
            parts = settings.template_repo.split("/")
            template_owner, template_repo = parts[0], parts[1]
            repo = await gh.create_repo_from_template(
                template_owner,
                template_repo,
                repo_name,
                description=repo_desc,
                private=private,
            )
            result["repo_created"] = True
            result["repo_url"] = repo.get("html_url", "")
            result["repo_full_name"] = repo.get("full_name", "")
            logger.info("Created GitHub repo: %s", result["repo_full_name"])

            # Clone and populate with project specs
            # Note: actual clone + populate happens during execution setup
            await gh.close()
        except Exception:
            logger.exception("Failed to create GitHub repo")
            result["repo_error"] = "Failed to create GitHub repo"
    else:
        result["repo_error"] = "GitHub token or template repo not configured"

    # Create Linear project
    if settings.linear_api_key and settings.linear_team_id:
        try:
            lc = LinearClient()
            linear_project = await lc.create_project(
                linear_name, [settings.linear_team_id]
            )
            result["linear_project_created"] = True
            result["linear_project_id"] = linear_project.id
            result["linear_project_url"] = linear_project.url
            logger.info("Created Linear project: %s", linear_project.id)
            await lc.close()
        except Exception:
            logger.exception("Failed to create Linear project")
            result["linear_error"] = "Failed to create Linear project"
    else:
        result["linear_error"] = "Linear API key or team ID not configured"

    return json.dumps(result)
