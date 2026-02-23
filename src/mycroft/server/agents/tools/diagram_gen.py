"""Mermaid diagram generation tool."""

from __future__ import annotations

import json
import logging
from typing import Any

from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

TOOL_DEF: dict[str, Any] = {
    "name": "diagram_gen",
    "description": (
        "Generate a Mermaid diagram and save it as a .mmd file in the project docs. "
        "Use this for use case diagrams, architecture diagrams, sequence diagrams, etc. "
        "The content should be valid Mermaid syntax."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename for the diagram (e.g. '01-use-case-diagram.mmd').",
            },
            "content": {
                "type": "string",
                "description": "The Mermaid diagram content.",
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

    logger.info("Saved diagram %s for project %s", filename, project.project_id)

    return json.dumps({"saved": True, "path": str(file_path)})
