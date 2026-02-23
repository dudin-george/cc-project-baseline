"""Tests for Linear GraphQL client."""

from __future__ import annotations

import httpx
import pytest

from mycroft.server.linear.client import LinearClient, LinearClientError
from mycroft.server.linear.models import LinearIssueCreateInput


_FAKE_REQUEST = httpx.Request("POST", "https://test.linear.app/graphql")


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json={"data": data}, request=_FAKE_REQUEST)


def _mock_error_response(errors: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"errors": errors}, request=_FAKE_REQUEST)


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "projectCreate": {
                "success": True,
                "project": {"id": "p1", "name": "Test", "slugId": "test", "url": "https://linear.app/p/test"},
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        project = await client.create_project("Test", ["team1"])
        assert project.id == "p1"
        assert project.name == "Test"
        assert project.slug_id == "test"
        await client.close()


class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "i1",
                    "identifier": "ABC-1",
                    "title": "Test Issue",
                    "url": "https://linear.app/issue/ABC-1",
                    "stateId": "s1",
                    "priority": 2,
                    "parentId": None,
                },
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        issue = await client.create_issue(
            LinearIssueCreateInput(title="Test Issue", team_id="team1", priority=2)
        )
        assert issue.id == "i1"
        assert issue.identifier == "ABC-1"
        assert issue.priority == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_with_parent(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "i2",
                    "identifier": "ABC-2",
                    "title": "Sub Issue",
                    "url": "",
                    "stateId": "s1",
                    "priority": 0,
                    "parentId": "i1",
                },
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        issue = await client.create_sub_issue(
            "i1", LinearIssueCreateInput(title="Sub Issue", team_id="team1")
        )
        assert issue.parent_id == "i1"
        await client.close()


class TestGetIssue:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issue": {
                "id": "i1",
                "identifier": "ABC-1",
                "title": "Test Issue",
                "description": "Some description",
                "url": "https://linear.app/issue/ABC-1",
                "stateId": "s1",
                "priority": 2,
                "parentId": None,
                "labels": {"nodes": [{"id": "l1", "name": "bug"}, {"id": "l2", "name": "urgent"}]},
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        issue = await client.get_issue("i1")
        assert issue.id == "i1"
        assert issue.identifier == "ABC-1"
        assert issue.description == "Some description"
        assert len(issue.labels) == 2
        assert issue.labels[0].name == "bug"
        assert issue.labels[1].name == "urgent"
        await client.close()


class TestListProjectIssues:
    @pytest.mark.asyncio
    async def test_single_page(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "project": {
                "issues": {
                    "nodes": [
                        {
                            "id": "i1", "identifier": "ABC-1", "title": "Story 1",
                            "url": "", "stateId": "s1", "priority": 0, "parentId": None,
                            "description": "", "labels": {"nodes": []},
                        },
                        {
                            "id": "i2", "identifier": "ABC-2", "title": "Task 1",
                            "url": "", "stateId": "s1", "priority": 0, "parentId": "i1",
                            "description": "", "labels": {"nodes": []},
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        issues = await client.list_project_issues("proj1")
        assert len(issues) == 2
        assert issues[0].id == "i1"
        assert issues[0].parent_id is None
        assert issues[1].parent_id == "i1"
        await client.close()

    @pytest.mark.asyncio
    async def test_pagination(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        call_count = {"n": 0}

        async def mock_post(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_response({
                    "project": {
                        "issues": {
                            "nodes": [
                                {
                                    "id": "i1", "identifier": "ABC-1", "title": "Issue 1",
                                    "url": "", "stateId": "s1", "priority": 0, "parentId": None,
                                    "description": "", "labels": {"nodes": []},
                                },
                            ],
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                        }
                    }
                })
            return _mock_response({
                "project": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "i2", "identifier": "ABC-2", "title": "Issue 2",
                                "url": "", "stateId": "s1", "priority": 0, "parentId": None,
                                "description": "", "labels": {"nodes": []},
                            },
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            })

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        issues = await client.list_project_issues("proj1")
        assert len(issues) == 2
        assert issues[0].id == "i1"
        assert issues[1].id == "i2"
        assert call_count["n"] == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_empty(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "project": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        issues = await client.list_project_issues("proj1")
        assert issues == []
        await client.close()


class TestUpdateIssueState:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({"issueUpdate": {"success": True}})
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        await client.update_issue_state("i1", "s2")
        await client.close()


class TestCreateIssueRelation:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issueRelationCreate": {
                "success": True,
                "issueRelation": {
                    "id": "r1",
                    "issueId": "i1",
                    "relatedIssueId": "i2",
                    "type": "blocks",
                },
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        rel = await client.create_issue_relation("i1", "i2", "blocks")
        assert rel.type == "blocks"
        assert rel.issue_id == "i1"
        await client.close()


class TestComments:
    @pytest.mark.asyncio
    async def test_add_comment(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "commentCreate": {
                "success": True,
                "comment": {"id": "c1", "body": "Hello", "userId": "u1", "createdAt": "2024-01-01"},
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        comment = await client.add_comment("i1", "Hello")
        assert comment.body == "Hello"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_comments(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issue": {
                "comments": {
                    "nodes": [
                        {"id": "c1", "body": "First", "userId": "u1", "createdAt": "2024-01-01"},
                        {"id": "c2", "body": "Second", "userId": "u2", "createdAt": "2024-01-02"},
                    ]
                }
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        comments = await client.get_issue_comments("i1")
        assert len(comments) == 2
        assert comments[0].body == "First"
        await client.close()


class TestWorkflowStatesAndLabels:
    @pytest.mark.asyncio
    async def test_get_workflow_states(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "workflowStates": {
                "nodes": [
                    {"id": "ws1", "name": "Backlog", "type": "backlog"},
                    {"id": "ws2", "name": "In Progress", "type": "started"},
                ]
            }
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        states = await client.get_workflow_states("team1")
        assert len(states) == 2
        assert states[0].name == "Backlog"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_labels(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issueLabels": {"nodes": [{"id": "l1", "name": "bug"}, {"id": "l2", "name": "feature"}]}
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        labels = await client.get_labels("team1")
        assert len(labels) == 2
        assert labels[1].name == "feature"
        await client.close()

    @pytest.mark.asyncio
    async def test_create_label(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_response({
            "issueLabelCreate": {"success": True, "issueLabel": {"id": "l3", "name": "blocker"}}
        })
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        label = await client.create_label("team1", "blocker")
        assert label.name == "blocker"
        await client.close()


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_graphql_error(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        resp = _mock_error_response([{"message": "Not found"}])
        monkeypatch.setattr(
            httpx.AsyncClient, "post", lambda self, *a, **kw: _async_return(resp)
        )
        with pytest.raises(LinearClientError):
            await client.create_project("Test", ["team1"])
        await client.close()

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")

        call_count = 0

        async def mock_post(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(429, headers={"retry-after": "0.01"}, request=_FAKE_REQUEST)
            return _mock_response({
                "projectCreate": {
                    "success": True,
                    "project": {"id": "p1", "name": "Test", "slugId": "", "url": ""},
                }
            })

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        project = await client.create_project("Test", ["team1"])
        assert project.id == "p1"
        assert call_count == 3
        await client.close()


class TestBatchHelpers:
    @pytest.mark.asyncio
    async def test_create_issues_batch(self, monkeypatch):
        client = LinearClient(api_key="test-key", api_url="https://test.linear.app/graphql")
        counter = {"n": 0}

        async def mock_post(self, *args, **kwargs):
            counter["n"] += 1
            return _mock_response({
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": f"i{counter['n']}",
                        "identifier": f"ABC-{counter['n']}",
                        "title": f"Issue {counter['n']}",
                        "url": "",
                        "stateId": "s1",
                        "priority": 0,
                        "parentId": None,
                    },
                }
            })

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        # Patch sleep to avoid test slowness
        monkeypatch.setattr("mycroft.server.linear.client.asyncio.sleep", _async_noop)
        inputs = [
            LinearIssueCreateInput(title=f"Issue {i}", team_id="team1")
            for i in range(3)
        ]
        issues = await client.create_issues_batch(inputs)
        assert len(issues) == 3
        assert issues[0].id == "i1"
        assert issues[2].id == "i3"
        await client.close()


# ── Helpers ──────────────────────────────────────────────────


async def _async_return(val):
    return val


async def _async_noop(*args, **kwargs):
    pass
