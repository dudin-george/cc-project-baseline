"""Web search tool wrapping Tavily for agent use."""

from __future__ import annotations

import json
from typing import Any

from mycroft.server.search.tavily import search as tavily_search

TOOL_DEF: dict[str, Any] = {
    "name": "web_search",
    "description": (
        "Search the web for information about competitors, market trends, "
        "technologies, or any topic relevant to the product being developed. "
        "Returns a list of search results with titles, URLs, and content snippets."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


async def execute(input_data: dict[str, Any]) -> str:
    query = input_data["query"]
    max_results = input_data.get("max_results", 5)
    results = await tavily_search(query, max_results=max_results)
    return json.dumps(results, indent=2)
