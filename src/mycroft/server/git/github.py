"""Async GitHub REST API client for repo and PR operations."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mycroft.server.settings import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised when the GitHub API returns an error."""


class GitHubClient:
    """Async GitHub REST client backed by httpx."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.github_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=GITHUB_API,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.request(method, path, json=json)
        if resp.status_code >= 400:
            raise GitHubClientError(
                f"GitHub API error {resp.status_code}: {resp.text}"
            )
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{owner}/{repo}")

    async def create_repo_from_template(
        self,
        template_owner: str,
        template_repo: str,
        name: str,
        owner: str | None = None,
        description: str = "",
        private: bool = True,
    ) -> dict[str, Any]:
        """Create a new repository from a template repository."""
        org = owner or settings.github_org
        body: dict[str, Any] = {
            "owner": org,
            "name": name,
            "description": description,
            "private": private,
            "include_all_branches": False,
        }
        return await self._request(
            "POST",
            f"/repos/{template_owner}/{template_repo}/generate",
            json=body,
        )

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a pull request and optionally add labels."""
        pr_data: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }
        pr = await self._request("POST", f"/repos/{owner}/{repo}/pulls", json=pr_data)

        if labels:
            pr_number = pr["number"]
            await self._request(
                "POST",
                f"/repos/{owner}/{repo}/issues/{pr_number}/labels",
                json={"labels": labels},
            )

        return pr

    async def add_labels_to_issue(
        self, owner: str, repo: str, issue_number: int, labels: list[str]
    ) -> list[dict[str, Any]]:
        return await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
