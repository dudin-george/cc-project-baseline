"""Async GraphQL client for the Linear API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from mycroft.server.linear.models import (
    LinearComment,
    LinearIssue,
    LinearIssueCreateInput,
    LinearIssueRelation,
    LinearLabel,
    LinearProject,
    LinearWorkflowState,
)
from mycroft.server.settings import settings

logger = logging.getLogger(__name__)

# Minimum delay between batch requests to avoid rate limits.
BATCH_DELAY = 0.1


class LinearClientError(Exception):
    """Raised when Linear API returns an error."""


class LinearClient:
    """Async Linear GraphQL client backed by httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.linear_api_key
        self._api_url = api_url or settings.linear_api_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._api_url,
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        """Execute a GraphQL request with retry on 429."""
        client = await self._get_client()
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(3):
            resp = await client.post("", json=payload)
            if resp.status_code == 429:
                wait = float(resp.headers.get("retry-after", 2 * (attempt + 1)))
                logger.warning("Linear rate-limited, waiting %.1fs", wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                raise LinearClientError(body["errors"])
            return body.get("data", {})

        raise LinearClientError("Rate limit exceeded after 3 retries")

    # ── Projects ─────────────────────────────────────────────

    async def create_project(self, name: str, team_ids: list[str]) -> LinearProject:
        query = """
        mutation($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project { id name slugId url }
            }
        }
        """
        variables = {"input": {"name": name, "teamIds": team_ids}}
        data = await self._request(query, variables)
        p = data["projectCreate"]["project"]
        return LinearProject(id=p["id"], name=p["name"], slug_id=p.get("slugId", ""), url=p.get("url", ""))

    # ── Issues ───────────────────────────────────────────────

    async def create_issue(self, inp: LinearIssueCreateInput) -> LinearIssue:
        query = """
        mutation($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue { id identifier title url stateId priority parentId }
            }
        }
        """
        variables: dict[str, Any] = {
            "input": {
                "title": inp.title,
                "description": inp.description,
                "teamId": inp.team_id,
                "priority": inp.priority,
            }
        }
        if inp.project_id:
            variables["input"]["projectId"] = inp.project_id
        if inp.parent_id:
            variables["input"]["parentId"] = inp.parent_id
        if inp.state_id:
            variables["input"]["stateId"] = inp.state_id
        if inp.label_ids:
            variables["input"]["labelIds"] = inp.label_ids
        if inp.assignee_id:
            variables["input"]["assigneeId"] = inp.assignee_id

        data = await self._request(query, variables)
        i = data["issueCreate"]["issue"]
        return LinearIssue(
            id=i["id"],
            identifier=i.get("identifier", ""),
            title=i.get("title", ""),
            url=i.get("url", ""),
            state_id=i.get("stateId", ""),
            priority=i.get("priority", 0),
            parent_id=i.get("parentId"),
        )

    async def get_issue(self, issue_id: str) -> LinearIssue:
        query = """
        query($id: String!) {
            issue(id: $id) {
                id identifier title url stateId priority parentId
                description
                labels { nodes { id name } }
            }
        }
        """
        data = await self._request(query, {"id": issue_id})
        i = data["issue"]
        labels = [
            LinearLabel(id=l["id"], name=l["name"])
            for l in i.get("labels", {}).get("nodes", [])
        ]
        return LinearIssue(
            id=i["id"],
            identifier=i.get("identifier", ""),
            title=i.get("title", ""),
            description=i.get("description", ""),
            url=i.get("url", ""),
            state_id=i.get("stateId", ""),
            priority=i.get("priority", 0),
            parent_id=i.get("parentId"),
            labels=labels,
        )

    async def create_sub_issue(
        self, parent_id: str, inp: LinearIssueCreateInput
    ) -> LinearIssue:
        inp.parent_id = parent_id
        return await self.create_issue(inp)

    async def update_issue_state(self, issue_id: str, state_id: str) -> None:
        query = """
        mutation($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) { success }
        }
        """
        await self._request(query, {"id": issue_id, "input": {"stateId": state_id}})

    # ── Relations ────────────────────────────────────────────

    async def create_issue_relation(
        self, issue_id: str, related_issue_id: str, relation_type: str = "blocks"
    ) -> LinearIssueRelation:
        query = """
        mutation($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
                issueRelation { id issueId relatedIssueId type }
            }
        }
        """
        variables = {
            "input": {
                "issueId": issue_id,
                "relatedIssueId": related_issue_id,
                "type": relation_type,
            }
        }
        data = await self._request(query, variables)
        r = data["issueRelationCreate"]["issueRelation"]
        return LinearIssueRelation(
            id=r["id"],
            issue_id=r["issueId"],
            related_issue_id=r["relatedIssueId"],
            type=r["type"],
        )

    # ── Comments ─────────────────────────────────────────────

    async def add_comment(self, issue_id: str, body: str) -> LinearComment:
        query = """
        mutation($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment { id body userId createdAt }
            }
        }
        """
        data = await self._request(query, {"input": {"issueId": issue_id, "body": body}})
        c = data["commentCreate"]["comment"]
        return LinearComment(
            id=c["id"],
            body=c.get("body", ""),
            user_id=c.get("userId", ""),
            created_at=c.get("createdAt", ""),
        )

    async def get_issue_comments(self, issue_id: str) -> list[LinearComment]:
        query = """
        query($id: String!) {
            issue(id: $id) {
                comments { nodes { id body userId createdAt } }
            }
        }
        """
        data = await self._request(query, {"id": issue_id})
        nodes = data.get("issue", {}).get("comments", {}).get("nodes", [])
        return [
            LinearComment(
                id=n["id"],
                body=n.get("body", ""),
                user_id=n.get("userId", ""),
                created_at=n.get("createdAt", ""),
            )
            for n in nodes
        ]

    # ── Workflow states & labels ─────────────────────────────

    async def get_workflow_states(self, team_id: str) -> list[LinearWorkflowState]:
        query = """
        query($teamId: String!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name type }
            }
        }
        """
        data = await self._request(query, {"teamId": team_id})
        nodes = data.get("workflowStates", {}).get("nodes", [])
        return [
            LinearWorkflowState(id=n["id"], name=n["name"], type=n.get("type", ""))
            for n in nodes
        ]

    async def get_labels(self, team_id: str) -> list[LinearLabel]:
        query = """
        query($teamId: String!) {
            issueLabels(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name }
            }
        }
        """
        data = await self._request(query, {"teamId": team_id})
        nodes = data.get("issueLabels", {}).get("nodes", [])
        return [LinearLabel(id=n["id"], name=n["name"]) for n in nodes]

    async def create_label(self, team_id: str, name: str, color: str = "#888888") -> LinearLabel:
        query = """
        mutation($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel { id name }
            }
        }
        """
        data = await self._request(
            query, {"input": {"teamId": team_id, "name": name, "color": color}}
        )
        lbl = data["issueLabelCreate"]["issueLabel"]
        return LinearLabel(id=lbl["id"], name=lbl["name"])

    # ── Webhooks ─────────────────────────────────────────────

    async def create_webhook(
        self,
        url: str,
        team_id: str,
        resource_types: list[str] | None = None,
    ) -> str:
        query = """
        mutation($input: WebhookCreateInput!) {
            webhookCreate(input: $input) {
                success
                webhook { id }
            }
        }
        """
        inp: dict[str, Any] = {"url": url, "teamId": team_id}
        if resource_types:
            inp["resourceTypes"] = resource_types
        data = await self._request(query, {"input": inp})
        return data["webhookCreate"]["webhook"]["id"]

    # ── Batch helpers ────────────────────────────────────────

    async def create_issues_batch(
        self, inputs: list[LinearIssueCreateInput]
    ) -> list[LinearIssue]:
        results = []
        for inp in inputs:
            results.append(await self.create_issue(inp))
            await asyncio.sleep(BATCH_DELAY)
        return results

    async def create_relations_batch(
        self, relations: list[tuple[str, str, str]]
    ) -> list[LinearIssueRelation]:
        """Create multiple issue relations. Each tuple: (issue_id, related_id, type)."""
        results = []
        for issue_id, related_id, rel_type in relations:
            results.append(await self.create_issue_relation(issue_id, related_id, rel_type))
            await asyncio.sleep(BATCH_DELAY)
        return results
