"""Regression guards for CP-1 C.7 (webhook DoS amplification).

Previously the GitLab webhook handler created a trace row (1 INSERT +
2 UPDATEs on the ``traces`` table) *before* verifying ``X-Gitlab-Token``.
An unauthenticated flood therefore drove sustained DB pressure without
paying the authentication cost first. Combined with C.1's event-loop
blocking on every DB write, this cascaded into legitimate-traffic
latency.

Fix: reorder ``gitlab_webhook`` to authenticate BEFORE any DB I/O.

The GitHub handler (``github_webhook``) already had the correct ordering
since CAB-1890 — HMAC signature verified at request entry, trace row
created afterwards. We pin that invariant here so a future refactor
cannot silently introduce the same bug on the GitHub side.

regression for CP-1 C.7
"""

from __future__ import annotations

import hmac
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

_TEST_SECRET = "test-webhook-secret"


def _minimal_push_payload() -> dict:
    """Smallest GitLab push payload the handler accepts."""
    return {
        "object_kind": "push",
        "event_name": "push",
        "ref": "refs/heads/main",
        "before": "0" * 40,
        "after": "a" * 40,
        "checkout_sha": "a" * 40,
        "project_id": 42,
        "project": {"path_with_namespace": "stoa/catalog"},
        "user_name": "alice",
        "user_username": "alice",
        "commits": [],
        "total_commits_count": 0,
    }


def _mock_trace_service_spy() -> tuple[MagicMock, MagicMock]:
    """Spy-flavoured TraceService: real AsyncMock, verifiable call counts."""
    mock_svc = MagicMock()
    mock_trace = MagicMock()
    mock_trace.id = "trace-001"
    mock_trace.status = MagicMock(value="success")
    mock_trace.total_duration_ms = 42
    mock_svc.create = AsyncMock(return_value=mock_trace)
    mock_svc.add_step = AsyncMock()
    mock_svc.complete = AsyncMock()
    return mock_svc, mock_trace


# ──────────────────────────────────────────────────────────────────
# GitLab: token verification MUST precede trace DB insert
# ──────────────────────────────────────────────────────────────────


class TestGitLabWebhookAuthFirst:
    def test_missing_token_rejects_without_db_write(self, app_with_cpi_admin, mock_db_session):
        """POST /webhooks/gitlab without X-Gitlab-Token → 401, zero trace insert."""
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_minimal_push_payload(),
                    headers={"X-Gitlab-Event": "Push Hook"},
                    # deliberately no X-Gitlab-Token
                )

        assert response.status_code == 401
        mock_svc.create.assert_not_called()
        mock_svc.add_step.assert_not_called()
        mock_svc.complete.assert_not_called()

    def test_wrong_token_rejects_without_db_write(self, app_with_cpi_admin, mock_db_session):
        """POST /webhooks/gitlab with an invalid token → 401, zero trace insert."""
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_minimal_push_payload(),
                    headers={
                        "X-Gitlab-Event": "Push Hook",
                        "X-Gitlab-Token": "not-the-right-secret",
                    },
                )

        assert response.status_code == 401
        mock_svc.create.assert_not_called()
        mock_svc.add_step.assert_not_called()
        mock_svc.complete.assert_not_called()

    def test_missing_server_side_secret_rejects_without_db_write(
        self, app_with_cpi_admin, mock_db_session
    ):
        """If GITLAB_WEBHOOK_SECRET is unset, every request is rejected — still no DB write."""
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr("")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_minimal_push_payload(),
                    headers={
                        "X-Gitlab-Event": "Push Hook",
                        "X-Gitlab-Token": _TEST_SECRET,
                    },
                )

        assert response.status_code == 401
        mock_svc.create.assert_not_called()

    def test_valid_token_still_persists_trace(self, app_with_cpi_admin, mock_db_session):
        """Happy path: valid token → trace row created, pipeline runs."""
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/gitlab",
                    json=_minimal_push_payload(),
                    headers={
                        "X-Gitlab-Event": "Push Hook",
                        "X-Gitlab-Token": _TEST_SECRET,
                    },
                )

        assert response.status_code == 200
        mock_svc.create.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# GitHub: HMAC verification MUST precede trace DB insert (pin invariant)
# ──────────────────────────────────────────────────────────────────


class TestGitHubWebhookInvariantPinned:
    """GitHub's webhook already authenticates before persisting the trace
    (CAB-1890 design). These tests pin that invariant so a future
    refactor cannot silently regress the ordering and re-introduce C.7
    on the GitHub side.
    """

    def _sign(self, body: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, "sha256").hexdigest()

    def test_missing_signature_rejects_without_db_write(
        self, app_with_cpi_admin, mock_db_session
    ):
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
        ):
            mock_settings.git.github.webhook_secret = SecretStr(_TEST_SECRET)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/github",
                    json={"ref": "refs/heads/main", "repository": {"full_name": "o/r"}},
                    headers={"X-GitHub-Event": "push"},
                    # deliberately no X-Hub-Signature-256
                )

        assert response.status_code == 401
        mock_svc.create.assert_not_called()
        mock_svc.add_step.assert_not_called()

    def test_invalid_signature_rejects_without_db_write(
        self, app_with_cpi_admin, mock_db_session
    ):
        mock_svc, _ = _mock_trace_service_spy()

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
        ):
            mock_settings.git.github.webhook_secret = SecretStr(_TEST_SECRET)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/webhooks/github",
                    json={"ref": "refs/heads/main", "repository": {"full_name": "o/r"}},
                    headers={
                        "X-GitHub-Event": "push",
                        "X-Hub-Signature-256": "sha256=" + "0" * 64,
                    },
                )

        assert response.status_code == 401
        mock_svc.create.assert_not_called()
