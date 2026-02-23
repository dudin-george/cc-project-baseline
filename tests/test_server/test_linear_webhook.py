"""Tests for Linear webhook handler."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycroft.server.linear.models import LinearWebhookPayload
from mycroft.server.linear.webhook import (
    clear_handlers,
    on_linear_event,
    register_handler,
    router,
)


@pytest.fixture()
def app():
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup_handlers():
    """Clear handlers before and after each test."""
    clear_handlers()
    yield
    clear_handlers()


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestWebhookEndpoint:
    def test_accepts_valid_payload(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")
        payload = {"action": "create", "type": "Issue", "data": {"id": "i1"}}
        resp = client.post("/webhooks/linear", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_verifies_signature(self, client, monkeypatch):
        secret = "test-secret"
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", secret)
        payload = {"action": "update", "type": "Issue", "data": {}}
        body = json.dumps(payload).encode()
        sig = _sign(body, secret)
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"content-type": "application/json", "linear-signature": sig},
        )
        assert resp.status_code == 200

    def test_rejects_bad_signature(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "secret")
        payload = {"action": "update", "type": "Issue", "data": {}}
        resp = client.post(
            "/webhooks/linear",
            json=payload,
            headers={"linear-signature": "bad"},
        )
        assert resp.status_code == 401

    def test_rejects_missing_signature_when_secret_configured(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "secret")
        payload = {"action": "update", "type": "Issue", "data": {}}
        resp = client.post("/webhooks/linear", json=payload)
        assert resp.status_code == 401


class TestHandlerRegistration:
    def test_decorator_registration(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")
        received = []

        @on_linear_event("create", "Issue")
        async def handler(payload: LinearWebhookPayload):
            received.append(payload)

        payload = {"action": "create", "type": "Issue", "data": {"id": "i1"}}
        client.post("/webhooks/linear", json=payload)
        assert len(received) == 1
        assert received[0].data == {"id": "i1"}

    def test_programmatic_registration(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")
        received = []

        async def handler(payload: LinearWebhookPayload):
            received.append(payload.action)

        register_handler("update", "Comment", handler)
        payload = {"action": "update", "type": "Comment", "data": {}}
        client.post("/webhooks/linear", json=payload)
        assert received == ["update"]

    def test_unmatched_event_no_error(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")
        payload = {"action": "delete", "type": "Issue", "data": {}}
        resp = client.post("/webhooks/linear", json=payload)
        assert resp.status_code == 200

    def test_multiple_handlers_same_event(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")
        calls = []

        @on_linear_event("update", "Issue")
        async def handler1(payload: LinearWebhookPayload):
            calls.append("h1")

        @on_linear_event("update", "Issue")
        async def handler2(payload: LinearWebhookPayload):
            calls.append("h2")

        payload = {"action": "update", "type": "Issue", "data": {}}
        client.post("/webhooks/linear", json=payload)
        assert calls == ["h1", "h2"]

    def test_handler_exception_doesnt_break_endpoint(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")

        @on_linear_event("create", "Issue")
        async def bad_handler(payload: LinearWebhookPayload):
            raise RuntimeError("boom")

        payload = {"action": "create", "type": "Issue", "data": {}}
        resp = client.post("/webhooks/linear", json=payload)
        assert resp.status_code == 200


class TestCommentBlockerWebhook:
    """Test that comment webhooks resolve blockers via blocker_webhook handler."""

    def test_comment_resolves_blocker(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")

        from mycroft.server.worker.blocker import PendingBlocker, _blockers, clear_all_blockers
        # Import the handler module to register its handler
        import mycroft.server.linear.blocker_webhook  # noqa: F401

        clear_all_blockers()
        try:
            # Set up a pending blocker with a known linear_issue_id
            blocker = PendingBlocker(
                blocker_id="b1",
                service_name="auth",
                question="How to handle OAuth?",
                linear_issue_id="issue-123",
            )
            _blockers["b1"] = blocker

            # POST a comment webhook for that issue
            payload = {
                "action": "create",
                "type": "Comment",
                "data": {"issueId": "issue-123", "body": "Use JWT tokens instead."},
            }
            resp = client.post("/webhooks/linear", json=payload)
            assert resp.status_code == 200

            # Blocker should be resolved
            assert blocker.event.is_set()
            assert blocker.answer == "Use JWT tokens instead."
        finally:
            clear_all_blockers()

    def test_comment_no_matching_blocker(self, client, monkeypatch):
        monkeypatch.setattr("mycroft.server.linear.webhook.settings.linear_webhook_secret", "")

        from mycroft.server.worker.blocker import clear_all_blockers
        import mycroft.server.linear.blocker_webhook  # noqa: F401

        clear_all_blockers()
        try:
            payload = {
                "action": "create",
                "type": "Comment",
                "data": {"issueId": "unknown-issue", "body": "Some comment"},
            }
            resp = client.post("/webhooks/linear", json=payload)
            assert resp.status_code == 200  # no error, just no match
        finally:
            clear_all_blockers()
