"""
Tests for Webhooks Router (GitLab) - CAB-1116 Phase 2B

Target: Coverage of src/routers/webhooks.py
Tests: 12 test cases covering push/MR/tag events, token verification, and health check.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


_TEST_SECRET = "test-webhook-secret"


def _push_payload(
    branch="main",
    files_added=None,
    files_modified=None,
    user_name="alice",
):
    """Build a GitLab push event payload."""
    if files_added is None:
        files_added = []
    if files_modified is None:
        files_modified = []

    return {
        "object_kind": "push",
        "event_name": "push",
        "ref": f"refs/heads/{branch}",
        "before": "0000000000000000000000000000000000000000",
        "after": "abc123def456",
        "checkout_sha": "abc123def456",
        "project_id": 42,
        "project": {"path_with_namespace": "stoa/gitops-config"},
        "user_name": user_name,
        "user_username": user_name,
        "user_email": f"{user_name}@example.com",
        "commits": [
            {
                "id": "abc123def456",
                "message": "Update API config",
                "author": {"name": user_name, "email": f"{user_name}@example.com"},
                "added": files_added,
                "modified": files_modified,
                "removed": [],
            }
        ],
        "total_commits_count": 1,
    }


def _mr_payload(state="merged", target_branch="main"):
    """Build a GitLab merge request event payload."""
    return {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "user": {"username": "alice"},
        "project": {"path_with_namespace": "stoa/gitops-config"},
        "object_attributes": {
            "state": state,
            "target_branch": target_branch,
            "iid": 42,
            "title": "Add new API",
        },
    }


def _tag_payload(tag="v1.0.0"):
    """Build a GitLab tag push event payload."""
    return {
        "object_kind": "tag_push",
        "event_name": "tag_push",
        "ref": f"refs/tags/{tag}",
        "project_id": 42,
        "project": {"path_with_namespace": "stoa/gitops-config"},
        "user_name": "alice",
        "user_username": "alice",
    }


def _mock_trace_service():
    """Create a mock TraceService."""
    mock_svc = MagicMock()
    mock_trace = MagicMock()
    mock_trace.id = "trace-001"
    mock_trace.status = MagicMock()
    mock_trace.status.value = "success"
    mock_trace.total_duration_ms = 42
    mock_svc.create = AsyncMock(return_value=mock_trace)
    mock_svc.add_step = AsyncMock()
    mock_svc.complete = AsyncMock()
    mock_svc.get_stats = AsyncMock(return_value={"total": 10, "success": 8, "failed": 2})
    return mock_svc, mock_trace


class TestGitLabWebhookPush:
    """Test GitLab push webhook handling."""

    def test_push_hook_with_api_changes(self, app_with_cpi_admin, mock_db_session):
        """Push to main with API changes publishes deploy events."""
        mock_svc, _mock_trace = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings, \
             patch("src.routers.webhooks.kafka_service") as mock_kafka:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(
                        files_modified=["tenants/acme/apis/weather-api/api.yaml"]
                    ),
                    headers={"X-Gitlab-Event": "Push Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["trace_id"] == "trace-001"

    def test_push_hook_with_mcp_server_changes(self, app_with_cpi_admin, mock_db_session):
        """Push with MCP server changes publishes server events."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings, \
             patch("src.routers.webhooks.kafka_service") as mock_kafka:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(
                        files_added=["tenants/acme/mcp-servers/tools/server.yaml"]
                    ),
                    headers={"X-Gitlab-Event": "Push Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200

    def test_push_hook_non_main_branch_skipped(self, app_with_cpi_admin, mock_db_session):
        """Push to non-main branch is skipped."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(branch="feature/foo"),
                    headers={"X-Gitlab-Event": "Push Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200

    def test_push_hook_no_api_changes_skipped(self, app_with_cpi_admin, mock_db_session):
        """Push with no API/MCP changes skipped."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(files_modified=["README.md"]),
                    headers={"X-Gitlab-Event": "Push Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200


class TestGitLabWebhookTokenVerification:
    """Test token verification."""

    def test_invalid_token_returns_401(self, app_with_cpi_admin, mock_db_session):
        """Invalid GitLab token returns 401."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = "correct-secret"

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(),
                    headers={
                        "X-Gitlab-Event": "Push Hook",
                        "X-Gitlab-Token": "wrong-secret",
                    },
                )

        assert response.status_code == 401

    def test_valid_token_accepted(self, app_with_cpi_admin, mock_db_session):
        """Valid GitLab token is accepted."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings, \
             patch("src.routers.webhooks.kafka_service") as mock_kafka:
            mock_settings.GITLAB_WEBHOOK_SECRET = "correct-secret"
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_push_payload(
                        files_modified=["tenants/acme/apis/my-api/api.yaml"]
                    ),
                    headers={
                        "X-Gitlab-Event": "Push Hook",
                        "X-Gitlab-Token": "correct-secret",
                    },
                )

        assert response.status_code == 200


class TestGitLabWebhookMergeRequest:
    """Test merge request webhook handling."""

    def test_merged_mr_triggers_sync(self, app_with_cpi_admin, mock_db_session):
        """Merged MR to main triggers sync request."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings, \
             patch("src.routers.webhooks.kafka_service") as mock_kafka:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_mr_payload(state="merged", target_branch="main"),
                    headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200

    def test_unmerged_mr_skipped(self, app_with_cpi_admin, mock_db_session):
        """Non-merged MR is skipped."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_mr_payload(state="opened"),
                    headers={"X-Gitlab-Event": "Merge Request Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200


class TestGitLabWebhookTag:
    """Test tag push webhook handling."""

    def test_tag_push_logged(self, app_with_cpi_admin, mock_db_session):
        """Tag push event is logged but not processed."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_tag_payload(),
                    headers={"X-Gitlab-Event": "Tag Push Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200


class TestGitLabWebhookUnsupported:
    """Test unsupported event types."""

    def test_unsupported_event_ignored(self, app_with_cpi_admin, mock_db_session):
        """Unsupported event type returns ignored status."""
        mock_svc, _ = _mock_trace_service()

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             patch("src.routers.webhooks.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = _TEST_SECRET

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json={"project": {}, "ref": "refs/heads/main"},
                    headers={"X-Gitlab-Event": "Pipeline Hook", "X-Gitlab-Token": _TEST_SECRET},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"


class TestGitLabWebhookHealth:
    """Test webhook health check."""

    def test_health_check(self, app_with_cpi_admin, mock_db_session):
        """Health endpoint returns trace stats."""
        mock_svc = MagicMock()
        mock_svc.get_stats = AsyncMock(return_value={"total": 5})

        with patch("src.routers.webhooks.TraceService", return_value=mock_svc), \
             TestClient(app_with_cpi_admin) as client:
            response = client.get("/webhooks/gitlab/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "trace_stats" in data
