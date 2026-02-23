"""Linear stories tool — create parent issues (stories) and sub-issues (tasks)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.server.linear.client import LinearClient
from mycroft.server.linear.models import LinearIssueCreateInput
from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "create_linear_stories",
    "description": (
        "Create Linear stories (parent issues) for each service and tasks (sub-issues) "
        "for each function/class group. Each story represents a service, and each task "
        "represents a unit of work within that service."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "linear_project_id": {
                "type": "string",
                "description": "The Linear project ID to create issues in.",
            },
            "stories": {
                "type": "array",
                "description": "List of stories (services) to create.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Story title, e.g. '[Auth] Authentication Service'.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Story description with service overview.",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Priority: 0=none, 1=urgent, 2=high, 3=medium, 4=low.",
                            "default": 3,
                        },
                        "tasks": {
                            "type": "array",
                            "description": "List of tasks within this story.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "priority": {"type": "integer", "default": 3},
                                },
                                "required": ["title", "description"],
                            },
                        },
                    },
                    "required": ["title", "description", "tasks"],
                },
            },
        },
        "required": ["linear_project_id", "stories"],
    },
}


async def execute(project: ProjectState, input_data: dict[str, Any]) -> str:
    linear_project_id = input_data["linear_project_id"]
    stories_input = input_data["stories"]

    lc = LinearClient()
    team_id = settings.linear_team_id

    created_stories: list[dict[str, Any]] = []

    try:
        for story_data in stories_input:
            # Create parent issue (story)
            story_input = LinearIssueCreateInput(
                title=story_data["title"],
                description=story_data["description"],
                team_id=team_id,
                project_id=linear_project_id,
                priority=story_data.get("priority", 3),
            )
            story = await lc.create_issue(story_input)
            logger.info("Created story: %s (%s)", story.identifier, story.title)

            created_tasks: list[dict[str, str]] = []
            for task_data in story_data.get("tasks", []):
                task_input = LinearIssueCreateInput(
                    title=task_data["title"],
                    description=task_data["description"],
                    team_id=team_id,
                    project_id=linear_project_id,
                    priority=task_data.get("priority", 3),
                )
                task = await lc.create_sub_issue(story.id, task_input)
                created_tasks.append({
                    "id": task.id,
                    "identifier": task.identifier,
                    "title": task.title,
                })
                logger.info("  Created task: %s (%s)", task.identifier, task.title)

            created_stories.append({
                "id": story.id,
                "identifier": story.identifier,
                "title": story.title,
                "tasks": created_tasks,
            })
    finally:
        await lc.close()

    return json.dumps({
        "stories_created": len(created_stories),
        "stories": created_stories,
    })
