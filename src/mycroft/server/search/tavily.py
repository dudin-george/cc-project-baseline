"""Tavily API async wrapper for web search."""

from __future__ import annotations

import logging
from typing import Any

from tavily import AsyncTavilyClient

from mycroft.server.settings import settings

logger = logging.getLogger(__name__)


async def search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the web via Tavily. Returns list of {title, url, content}."""
    if not settings.tavily_api_key:
        logger.warning("Tavily API key not configured, returning empty results")
        return []

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    response = await client.search(query=query, max_results=max_results)

    results = []
    for r in response.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        })
    return results
