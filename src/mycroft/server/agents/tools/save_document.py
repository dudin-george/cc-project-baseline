"""Save document tool: render template → write to project docs → git commit + push."""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "save_document",
    "description": (
        "Save or update a document in the project's docs directory. "
        "Use this to persist idea documents, use case specs, architecture docs, "
        "and service specifications. The document will also be committed to the "
        "docs git repository if configured."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "The filename relative to the project docs directory. "
                    "Examples: '00-idea.md', '01-use-cases.md', 'services/svc-auth.md'"
                ),
            },
            "content": {
                "type": "string",
                "description": "The full markdown content of the document.",
            },
        },
        "required": ["filename", "content"],
    },
}


async def execute(project: ProjectState, input_data: dict[str, Any]) -> str:
    filename = input_data["filename"]
    content = input_data["content"]

    docs_dir = project.project_dir / "docs"
    file_path = docs_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)

    logger.info("Saved document %s for project %s", filename, project.project_id)

    # Push to git docs repo if configured
    pushed = False
    if settings.docs_repo_url:
        try:
            from mycroft.server.git.docs_repo import commit_and_push
            await commit_and_push(project, filename, content)
            pushed = True
        except Exception:
            logger.exception("Failed to push document to git repo")

    return json.dumps({
        "saved": True,
        "path": str(file_path),
        "pushed_to_git": pushed,
    })
