"""Tests for Webhooks Router — GitLab webhook handlers (GitOps with tracing).

Covers: GET /webhooks/gitlab/health, POST /webhooks/gitlab

Note: This router has NO auth dependency — uses X-Gitlab-Token header instead.
      The TraceService and kafka_service are patched at the router module level.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

TRACE_SVC_PATH = "src.routers.webhooks.TraceService"
KAFKA_SVC_PATH = "src.routers.webhooks.kafka_service"
SETTINGS_PATH = "src.routers.webhooks.settings"

VALID_TOKEN = "my-secret-gitlab-token"

_PUSH_PAYLOAD = {
    "object_kind": "push",
    "event_name": "push",
    "ref": "refs/heads/main",
    "before": "abc123",
    "after": "def456",
    "project_id": 42,
    "user_name": "Alice",
    "user_username": "alice",
    "user_email": "alice@example.com",
    "project": {"path_with_namespace": "acme/api-specs"},
    "commits": [
        {
            "id": "def456",
            "message": "Add new API spec",
            "author": {"name": "Alice", "email": "alice@example.com"},
            "added": ["tenants/acme/apis/weather/openapi.yaml"],
            "modified": [],
            "removed": [],
        }
    ],
    "total_commits_count": 1,
}

_MR_PAYLOAD = {
    "object_kind": "merge_request",
    "event_type": "merge_request",
    "user": {"username": "bob"},
    "project": {"path_with_namespace": "acme/api-specs"},
    "object_attributes": {
        "state": "merged",
        "target_branch": "main",
        "iid": 7,
        "title": "Add new endpoint",
    },
}

_TAG_PAYLOAD = {
    "object_kind": "tag_push",
    "ref": "refs/tags/v1.0.0",
    "project_id": 42,
    "user_name": "Alice",
    "user_username": "alice",
    "project": {"path_with_namespace": "acme/api-specs"},
    "commits": [],
}


def _build_no_auth_client(app, mock_db_session):
    """Build a TestClient with only DB override (no auth override for webhooks)."""
    from src.database import get_db

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _make_trace_service_mock():
    """Build a complete TraceService mock."""
    trace = MagicMock()
    trace.id = "trace-abc-123"
    trace.status = MagicMock()
    trace.status.value = "success"
    trace.total_duration_ms = 42
    trace.tenant_id = None
    trace.api_name = None
    trace.environment = None

    svc = MagicMock()
    svc.create = AsyncMock(return_value=trace)
    svc.add_step = AsyncMock()
    svc.complete = AsyncMock()
    svc.get_stats = AsyncMock(return_value={"total": 5, "success": 4, "failed": 1})
    return svc, trace


class TestWebhookHealth:
    """Tests for GET /webhooks/gitlab/health."""

    def test_health_returns_200(self, app, mock_db_session):
        svc, _ = _make_trace_service_mock()

        with patch(TRACE_SVC_PATH, return_value=svc):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.get("/webhooks/gitlab/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "trace_stats" in data
        assert "supported_events" in data


class TestGitlabWebhookPost:
    """Tests for POST /webhooks/gitlab."""

    def test_push_hook_success(self, app, mock_db_session):
        """Valid push hook with correct token is processed."""
        svc, _trace = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock(return_value="event-id-1")

        with (
            patch(TRACE_SVC_PATH, return_value=svc),
            patch(SETTINGS_PATH, mock_settings),
            patch(KAFKA_SVC_PATH, mock_kafka),
        ):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=_PUSH_PAYLOAD,
                headers={
                    "X-Gitlab-Token": VALID_TOKEN,
                    "X-Gitlab-Event": "Push Hook",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["trace_id"] == "trace-abc-123"

    def test_push_hook_401_missing_token(self, app, mock_db_session):
        """Missing X-Gitlab-Token returns 401."""
        svc, _ = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        with patch(TRACE_SVC_PATH, return_value=svc), patch(SETTINGS_PATH, mock_settings):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=_PUSH_PAYLOAD,
                headers={"X-Gitlab-Event": "Push Hook"},
            )

        assert resp.status_code == 401

    def test_push_hook_401_invalid_token(self, app, mock_db_session):
        """Wrong X-Gitlab-Token returns 401."""
        svc, _ = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        with patch(TRACE_SVC_PATH, return_value=svc), patch(SETTINGS_PATH, mock_settings):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=_PUSH_PAYLOAD,
                headers={
                    "X-Gitlab-Token": "wrong-token",
                    "X-Gitlab-Event": "Push Hook",
                },
            )

        assert resp.status_code == 401

    def test_merge_request_hook_success(self, app, mock_db_session):
        """Merge request hook is processed correctly."""
        svc, _trace = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock(return_value="event-id-2")

        with (
            patch(TRACE_SVC_PATH, return_value=svc),
            patch(SETTINGS_PATH, mock_settings),
            patch(KAFKA_SVC_PATH, mock_kafka),
        ):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=_MR_PAYLOAD,
                headers={
                    "X-Gitlab-Token": VALID_TOKEN,
                    "X-Gitlab-Event": "Merge Request Hook",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"

    def test_unsupported_event_type_ignored(self, app, mock_db_session):
        """Unknown event type returns status=ignored."""
        svc, _ = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        with patch(TRACE_SVC_PATH, return_value=svc), patch(SETTINGS_PATH, mock_settings):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json={"object_kind": "issue", "project": {}, "project_id": 1},
                headers={
                    "X-Gitlab-Token": VALID_TOKEN,
                    "X-Gitlab-Event": "Issue Hook",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_push_to_non_main_branch_skipped(self, app, mock_db_session):
        """Push to non-main branch is still processed (returns status=processed)."""
        svc, _ = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        feature_push = {**_PUSH_PAYLOAD, "ref": "refs/heads/feature/my-feature"}

        with patch(TRACE_SVC_PATH, return_value=svc), patch(SETTINGS_PATH, mock_settings):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=feature_push,
                headers={
                    "X-Gitlab-Token": VALID_TOKEN,
                    "X-Gitlab-Event": "Push Hook",
                },
            )

        # Router processes it and returns success (branch check is internal)
        assert resp.status_code == 200

    def test_tag_push_hook_success(self, app, mock_db_session):
        """Tag push hook is handled correctly."""
        svc, _trace = _make_trace_service_mock()
        mock_settings = MagicMock()
        mock_settings.GITLAB_WEBHOOK_SECRET = VALID_TOKEN

        with patch(TRACE_SVC_PATH, return_value=svc), patch(SETTINGS_PATH, mock_settings):
            client = _build_no_auth_client(app, mock_db_session)
            resp = client.post(
                "/webhooks/gitlab",
                json=_TAG_PAYLOAD,
                headers={
                    "X-Gitlab-Token": VALID_TOKEN,
                    "X-Gitlab-Event": "Tag Push Hook",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"
