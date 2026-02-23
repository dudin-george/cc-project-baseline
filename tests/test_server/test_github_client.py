"""Tests for GitHub REST API client."""

from __future__ import annotations

import httpx
import pytest

from mycroft.server.git.github import GitHubClient, GitHubClientError

_FAKE_REQUEST = httpx.Request("GET", "https://api.github.com")


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data, request=_FAKE_REQUEST)


async def _async_return(val):
    return val


class TestGetRepo:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = GitHubClient(token="test-token")
        resp = _mock_response({"id": 1, "name": "my-repo", "full_name": "org/my-repo"})
        monkeypatch.setattr(
            httpx.AsyncClient, "request", lambda self, *a, **kw: _async_return(resp)
        )
        repo = await client.get_repo("org", "my-repo")
        assert repo["name"] == "my-repo"
        await client.close()


class TestCreateRepoFromTemplate:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = GitHubClient(token="test-token")
        resp = _mock_response({
            "id": 2,
            "name": "new-project",
            "full_name": "org/new-project",
            "html_url": "https://github.com/org/new-project",
        }, status_code=201)
        monkeypatch.setattr(
            httpx.AsyncClient, "request", lambda self, *a, **kw: _async_return(resp)
        )
        repo = await client.create_repo_from_template(
            "org", "template-repo", "new-project", owner="org"
        )
        assert repo["name"] == "new-project"
        await client.close()

    @pytest.mark.asyncio
    async def test_error(self, monkeypatch):
        client = GitHubClient(token="test-token")
        resp = httpx.Response(
            422,
            json={"message": "Validation Failed"},
            request=_FAKE_REQUEST,
        )
        monkeypatch.setattr(
            httpx.AsyncClient, "request", lambda self, *a, **kw: _async_return(resp)
        )
        with pytest.raises(GitHubClientError, match="422"):
            await client.create_repo_from_template(
                "org", "template-repo", "new-project"
            )
        await client.close()


class TestCreatePullRequest:
    @pytest.mark.asyncio
    async def test_success_without_labels(self, monkeypatch):
        client = GitHubClient(token="test-token")
        resp = _mock_response({
            "number": 42,
            "title": "feat: add auth",
            "html_url": "https://github.com/org/repo/pull/42",
        }, status_code=201)
        monkeypatch.setattr(
            httpx.AsyncClient, "request", lambda self, *a, **kw: _async_return(resp)
        )
        pr = await client.create_pull_request(
            "org", "repo", "feat: add auth", "mycroft/auth-1"
        )
        assert pr["number"] == 42
        await client.close()

    @pytest.mark.asyncio
    async def test_success_with_labels(self, monkeypatch):
        client = GitHubClient(token="test-token")
        calls = []

        async def mock_request(self, method, path, **kwargs):
            calls.append((method, path))
            if method == "POST" and "/pulls" in path:
                return _mock_response({"number": 10, "title": "test"}, 201)
            return _mock_response([{"name": "auto-merge"}])

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)
        pr = await client.create_pull_request(
            "org", "repo", "test", "branch", labels=["auto-merge"]
        )
        assert pr["number"] == 10
        assert len(calls) == 2
        assert "/pulls" in calls[0][1]
        assert "/labels" in calls[1][1]
        await client.close()
