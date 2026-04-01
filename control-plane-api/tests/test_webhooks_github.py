"""Tests for GitHub webhook endpoint + signature verification (CAB-1890).

Covers:
- verify_github_signature (valid HMAC, invalid, missing, no secret)
- POST /webhooks/github push event with valid HMAC → 200
- POST /webhooks/github push event with invalid HMAC → 401
- POST /webhooks/github push event with missing signature → 401
- POST /webhooks/github pull_request merged event → 200
- POST /webhooks/github unsupported event → 200 (processed, no Kafka)
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.routers.webhooks import verify_github_signature

# ─────────────────────────────────────────────
# verify_github_signature unit tests
# ─────────────────────────────────────────────


class TestVerifyGithubSignature:
    def test_valid_signature(self):
        secret = "test-secret"
        body = b'{"ref":"refs/heads/main"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_github_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        assert verify_github_signature(b"body", "sha256=bad", "secret") is False

    def test_missing_signature(self):
        assert verify_github_signature(b"body", None, "secret") is False

    def test_no_secret_configured(self):
        assert verify_github_signature(b"body", "sha256=x", "") is False

    def test_signature_without_prefix(self):
        assert verify_github_signature(b"body", "noprefixhex", "secret") is False

    def test_empty_body(self):
        secret = "test-secret"
        body = b""
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_github_signature(body, sig, secret) is True


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

WEBHOOK_SECRET = "test-webhook-secret-123"


def _sign_payload(payload: dict, secret: str = WEBHOOK_SECRET) -> str:
    """Generate HMAC-SHA256 signature for a payload."""
    body = json.dumps(payload).encode()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _push_payload(
    repo: str = "stoa-platform/stoa-catalog",
    branch: str = "main",
    author: str = "test-user",
    commit_sha: str = "abc123def456",
) -> dict:
    """Build a minimal GitHub push webhook payload."""
    return {
        "ref": f"refs/heads/{branch}",
        "repository": {"full_name": repo},
        "sender": {"login": author},
        "head_commit": {
            "id": commit_sha,
            "message": "feat: add new API",
            "author": {"name": author, "email": f"{author}@example.com"},
        },
        "commits": [
            {
                "id": commit_sha,
                "message": "feat: add new API",
                "added": ["tenants/acme/apis/weather/api.yaml"],
                "modified": [],
                "removed": [],
            }
        ],
    }


def _pull_request_payload(
    action: str = "closed",
    merged: bool = True,
    repo: str = "stoa-platform/stoa-catalog",
    pr_number: int = 42,
) -> dict:
    """Build a minimal GitHub pull_request webhook payload."""
    return {
        "action": action,
        "repository": {"full_name": repo},
        "sender": {"login": "test-user"},
        "pull_request": {
            "number": pr_number,
            "merged": merged,
            "title": "feat: add weather API",
            "merge_commit_sha": "merge123abc",
            "user": {"login": "test-user"},
            "head": {"ref": "feat/weather-api"},
        },
    }


def _mock_trace():
    """Create a mock trace object returned by TraceService.create."""
    trace = MagicMock()
    trace.id = "trace-uuid-123"
    trace.status = MagicMock(value="success")
    trace.total_duration_ms = 42
    return trace


# ─────────────────────────────────────────────
# GitHub webhook endpoint integration tests
# ─────────────────────────────────────────────


class TestGithubWebhookEndpoint:
    """Integration tests for POST /webhooks/github."""

    @pytest.fixture
    def mock_deps(self):
        """Patch TraceService, Kafka, and HMAC verification for webhook endpoint tests."""
        mock_trace = _mock_trace()
        with (
            patch("src.routers.webhooks.TraceService") as mock_trace_svc_cls,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
            patch("src.routers.webhooks.verify_github_signature", return_value=True) as mock_verify,
        ):
            mock_trace_svc = AsyncMock()
            mock_trace_svc.create.return_value = mock_trace
            mock_trace_svc.add_step = AsyncMock()
            mock_trace_svc.complete = AsyncMock()
            mock_trace_svc_cls.return_value = mock_trace_svc
            mock_kafka.publish = AsyncMock(return_value="event-id-1")
            yield {
                "trace_service": mock_trace_svc,
                "kafka": mock_kafka,
                "verify": mock_verify,
                "trace": mock_trace,
            }

    @pytest.fixture
    async def test_client(self):
        """Create async test client with DB dependency override."""
        from src.main import app

        app.dependency_overrides = {}
        # Override DB dependency
        from src.database import get_db

        mock_db = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_push_event_valid_hmac(self, test_client, mock_deps):
        payload = _push_payload()
        sig = _sign_payload(payload)
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["event"] == "push"
        assert data["trace_id"] == "trace-uuid-123"

    async def test_push_event_invalid_hmac(self, test_client, mock_deps):
        mock_deps["verify"].return_value = False
        payload = _push_payload()
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=badbadbadbad",
            },
        )
        assert resp.status_code == 401
        assert "Invalid signature" in resp.json()["detail"]

    async def test_push_event_missing_signature(self, test_client, mock_deps):
        mock_deps["verify"].return_value = False
        payload = _push_payload()
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 401

    async def test_pull_request_merged(self, test_client, mock_deps):
        payload = _pull_request_payload(action="closed", merged=True)
        sig = _sign_payload(payload)
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event"] == "pull_request"
        # Verify Kafka sync-gitops event was published
        mock_deps["kafka"].publish.assert_called()

    async def test_pull_request_not_merged(self, test_client, mock_deps):
        payload = _pull_request_payload(action="closed", merged=False)
        sig = _sign_payload(payload)
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        # Kafka should NOT receive sync-gitops (PR was not merged)
        calls = mock_deps["kafka"].publish.call_args_list
        sync_gitops_calls = [c for c in calls if "sync-gitops" in str(c)]
        assert len(sync_gitops_calls) == 0

    async def test_unsupported_event_processed(self, test_client, mock_deps):
        payload = {"action": "created", "repository": {"full_name": "stoa/catalog"}, "sender": {"login": "bot"}}
        sig = _sign_payload(payload)
        resp = await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["event"] == "issues"

    async def test_push_publishes_kafka_sync_catalog(self, test_client, mock_deps):
        payload = _push_payload()
        sig = _sign_payload(payload)
        await test_client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
        # Verify Kafka received sync-catalog event
        mock_deps["kafka"].publish.assert_called_once()
        call_kwargs = mock_deps["kafka"].publish.call_args
        assert call_kwargs.kwargs.get("event_type") == "sync-catalog" or (
            len(call_kwargs.args) >= 2 and "sync-catalog" in str(call_kwargs)
        )
