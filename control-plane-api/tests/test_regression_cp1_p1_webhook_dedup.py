"""Regression guards for CP-1 P1 H.1 — webhook replay dedup.

GitHub and GitLab re-deliver the same webhook on timeout, on manual
redelivery, or on transient failures. Prior to this fix the pipeline
ran twice: Kafka publish x2, trace x2. The new state machine keyed on
(source, delivery_id) ensures:

1. First delivery passes auth and is marked with a ``claim`` state.
2. On successful pipeline completion, the claim is promoted to ``done``
   and a cached response is stored.
3. A redelivery with the same id while ``done`` returns
   ``status="duplicate"`` with zero side effects.
4. A redelivery while another process is still on ``claim`` returns
   ``status="in-flight"``.
5. On pipeline failure the claim is **released**, so the next retry
   does NOT get a spurious "duplicate forever" — the event cannot be
   lost because a first attempt failed midway.

Key contract pinned here:
- GitLab dedup primary key is ``Idempotency-Key``. Fallback:
  ``X-Gitlab-Webhook-UUID``. ``X-Gitlab-Event-UUID`` is NEVER the key
  (shared across recursive webhooks — would drop legitimate events).
- GitHub dedup key is ``X-GitHub-Delivery``.

regression for CP-1 H.1
"""

from __future__ import annotations

import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.services.webhook_dedup import (
    DedupVerdict,
    WebhookDedupCache,
    github_delivery_id,
    gitlab_delivery_id,
    webhook_dedup_cache,
)

_TEST_SECRET = "test-webhook-secret"


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _clean_cache():
    """Reset the module-level cache between tests."""
    await webhook_dedup_cache.reset()
    yield
    await webhook_dedup_cache.reset()


def _minimal_gitlab_push_payload() -> dict:
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
    mock_svc = MagicMock()
    mock_trace = MagicMock()
    mock_trace.id = "trace-001"
    mock_trace.status = MagicMock(value="success")
    mock_trace.total_duration_ms = 42
    mock_svc.create = AsyncMock(return_value=mock_trace)
    mock_svc.add_step = AsyncMock()
    mock_svc.complete = AsyncMock()
    return mock_svc, mock_trace


def _sign_github(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, "sha256").hexdigest()


# ──────────────────────────────────────────────────────────────────
# Unit-level — the dedup cache state machine
# ──────────────────────────────────────────────────────────────────


class TestDedupCacheStateMachine:
    @pytest.mark.asyncio
    async def test_first_claim_is_new(self):
        """regression for CP-1 H.1"""
        cache = WebhookDedupCache()
        verdict, cached = await cache.claim("github", "id-1")
        assert verdict is DedupVerdict.NEW
        assert cached is None

    @pytest.mark.asyncio
    async def test_second_claim_while_in_flight(self):
        """regression for CP-1 H.1"""
        cache = WebhookDedupCache()
        await cache.claim("github", "id-1")
        verdict, _ = await cache.claim("github", "id-1")
        assert verdict is DedupVerdict.IN_FLIGHT

    @pytest.mark.asyncio
    async def test_claim_after_done_is_duplicate(self):
        """regression for CP-1 H.1"""
        cache = WebhookDedupCache()
        await cache.claim("github", "id-1")
        await cache.mark_done("github", "id-1", {"foo": "bar"})
        verdict, cached = await cache.claim("github", "id-1")
        assert verdict is DedupVerdict.DUPLICATE
        assert cached == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_release_after_failure_allows_retry(self):
        """The critical H.1 property: a failed first attempt must not
        turn the retry into 'duplicate forever' and drop the event.

        regression for CP-1 H.1
        """
        cache = WebhookDedupCache()
        await cache.claim("github", "id-1")
        await cache.release("github", "id-1")
        verdict, _ = await cache.claim("github", "id-1")
        assert verdict is DedupVerdict.NEW  # retry, not DUPLICATE

    @pytest.mark.asyncio
    async def test_sources_do_not_collide(self):
        """github:id-1 and gitlab:id-1 are separate keys.

        regression for CP-1 H.1
        """
        cache = WebhookDedupCache()
        v1, _ = await cache.claim("github", "id-1")
        v2, _ = await cache.claim("gitlab", "id-1")
        assert v1 is DedupVerdict.NEW
        assert v2 is DedupVerdict.NEW

    @pytest.mark.asyncio
    async def test_capacity_evicts_oldest(self):
        """regression for CP-1 H.1"""
        cache = WebhookDedupCache(capacity=2)
        await cache.claim("github", "id-1")
        await cache.claim("github", "id-2")
        await cache.claim("github", "id-3")
        assert await cache.size() == 2

    @pytest.mark.asyncio
    async def test_ttl_expires_entries(self):
        """regression for CP-1 H.1"""
        cache = WebhookDedupCache(ttl_seconds=0.05)
        await cache.claim("github", "id-1")
        await cache.mark_done("github", "id-1", {"r": 1})
        # Advance time beyond TTL.
        import asyncio

        await asyncio.sleep(0.06)
        verdict, _ = await cache.claim("github", "id-1")
        assert verdict is DedupVerdict.NEW  # entry expired, retry is new


# ──────────────────────────────────────────────────────────────────
# Unit-level — dedup key priority (the "never Event-UUID" rule)
# ──────────────────────────────────────────────────────────────────


class TestGitLabDedupKeyPriority:
    def test_idempotency_key_wins_over_webhook_uuid(self):
        """regression for CP-1 H.1"""
        key = gitlab_delivery_id("idem-42", "webhook-7")
        assert key == "gitlab:idem:idem-42"

    def test_falls_back_to_webhook_uuid(self):
        """regression for CP-1 H.1"""
        key = gitlab_delivery_id(None, "webhook-7")
        assert key == "gitlab:webhook:webhook-7"

    def test_none_when_both_absent(self):
        """regression for CP-1 H.1"""
        assert gitlab_delivery_id(None, None) is None
        assert gitlab_delivery_id("", "") is None

    def test_idempotency_key_namespace_is_distinct(self):
        """Idempotency-Key and Webhook-UUID use DIFFERENT namespaces so
        a webhook with the same raw string under different header types
        is not conflated.

        regression for CP-1 H.1
        """
        k1 = gitlab_delivery_id("42", None)
        k2 = gitlab_delivery_id(None, "42")
        assert k1 != k2


class TestGitHubDedupKey:
    def test_delivery_header_becomes_key(self):
        """regression for CP-1 H.1"""
        assert github_delivery_id("abc-123") == "github:abc-123"

    def test_none_when_header_missing(self):
        """regression for CP-1 H.1"""
        assert github_delivery_id(None) is None
        assert github_delivery_id("") is None


# ──────────────────────────────────────────────────────────────────
# HTTP-level — GitLab webhook dedup
# ──────────────────────────────────────────────────────────────────


class TestGitLabWebhookDedupHTTP:
    def test_replayed_delivery_via_idempotency_key_is_duplicate(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Two POSTs with identical Idempotency-Key → first = processed,
        second = duplicate (no second Kafka publish, no second trace).

        regression for CP-1 H.1
        """
        mock_svc, _ = _mock_trace_service_spy()
        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            headers = {
                "X-Gitlab-Event": "Push Hook",
                "X-Gitlab-Token": _TEST_SECRET,
                "Idempotency-Key": "idem-abc-123",
            }
            with TestClient(app_with_cpi_admin) as client:
                r1 = client.post(
                    "/webhooks/gitlab", json=_minimal_gitlab_push_payload(), headers=headers
                )
                r2 = client.post(
                    "/webhooks/gitlab", json=_minimal_gitlab_push_payload(), headers=headers
                )

        assert r1.status_code == 200
        assert r1.json()["status"] in {"processed", "ignored"}
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"
        # Only ONE trace row created across both requests.
        assert mock_svc.create.call_count == 1

    def test_webhook_uuid_fallback_when_no_idempotency_key(
        self, app_with_cpi_admin, mock_db_session
    ):
        """regression for CP-1 H.1"""
        mock_svc, _ = _mock_trace_service_spy()
        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            headers = {
                "X-Gitlab-Event": "Push Hook",
                "X-Gitlab-Token": _TEST_SECRET,
                "X-Gitlab-Webhook-UUID": "webhook-xyz-999",
            }
            with TestClient(app_with_cpi_admin) as client:
                r1 = client.post(
                    "/webhooks/gitlab", json=_minimal_gitlab_push_payload(), headers=headers
                )
                r2 = client.post(
                    "/webhooks/gitlab", json=_minimal_gitlab_push_payload(), headers=headers
                )

        assert r1.status_code == 200
        assert r2.json()["status"] == "duplicate"
        assert mock_svc.create.call_count == 1

    def test_missing_dedup_header_still_processes(
        self, app_with_cpi_admin, mock_db_session
    ):
        """No Idempotency-Key AND no Webhook-UUID → process (with warning
        log). Backward-compat for older GitLab deployments.

        regression for CP-1 H.1
        """
        mock_svc, _ = _mock_trace_service_spy()
        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.gitlab.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            headers = {
                "X-Gitlab-Event": "Push Hook",
                "X-Gitlab-Token": _TEST_SECRET,
            }
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post(
                    "/webhooks/gitlab", json=_minimal_gitlab_push_payload(), headers=headers
                )

        assert resp.status_code == 200
        # No dedup key means the trace is still created — and a second
        # request would also create a trace (can't dedup without a key).
        assert mock_svc.create.call_count == 1


# ──────────────────────────────────────────────────────────────────
# HTTP-level — GitHub webhook dedup
# ──────────────────────────────────────────────────────────────────


class TestGitHubWebhookDedupHTTP:
    def test_replayed_delivery_returns_duplicate(
        self, app_with_cpi_admin, mock_db_session
    ):
        """regression for CP-1 H.1"""
        mock_svc, _ = _mock_trace_service_spy()
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "stoa/catalog"},
            "head_commit": {"id": "abc123", "message": "x", "author": {"name": "alice"}},
            "sender": {"login": "alice"},
        }
        import json

        body = json.dumps(payload).encode()
        sig = _sign_github(body, _TEST_SECRET)

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.github.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            headers = {
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Delivery": "delivery-abc-123",
                "Content-Type": "application/json",
            }
            with TestClient(app_with_cpi_admin) as client:
                r1 = client.post("/webhooks/github", content=body, headers=headers)
                r2 = client.post("/webhooks/github", content=body, headers=headers)

        assert r1.status_code == 200
        assert r1.json()["status"] == "processed"
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"
        assert mock_svc.create.call_count == 1

    def test_claim_released_on_failure_allows_retry(
        self, app_with_cpi_admin, mock_db_session
    ):
        """First attempt passes auth but fails mid-pipeline → claim
        released → retry is NOT treated as duplicate.

        regression for CP-1 H.1
        """
        mock_svc, _ = _mock_trace_service_spy()
        # First call: service.complete raises. Second call: succeeds.
        mock_svc.complete = AsyncMock(side_effect=[RuntimeError("kafka boom"), None])
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "stoa/catalog"},
            "head_commit": {"id": "abc123", "message": "x", "author": {"name": "alice"}},
            "sender": {"login": "alice"},
        }
        import json

        body = json.dumps(payload).encode()
        sig = _sign_github(body, _TEST_SECRET)

        with (
            patch("src.routers.webhooks.TraceService", return_value=mock_svc),
            patch("src.routers.webhooks.settings") as mock_settings,
            patch("src.routers.webhooks.kafka_service") as mock_kafka,
        ):
            mock_settings.git.github.webhook_secret = SecretStr(_TEST_SECRET)
            mock_kafka.publish = AsyncMock(return_value="evt-1")

            headers = {
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Delivery": "delivery-ff-1",
                "Content-Type": "application/json",
            }
            with TestClient(app_with_cpi_admin) as client:
                r1 = client.post("/webhooks/github", content=body, headers=headers)
                r2 = client.post("/webhooks/github", content=body, headers=headers)

        assert r1.status_code == 500  # first failed
        assert r1.json()["detail"] == "Internal error processing webhook"
        # r2 must be NEW processing, not DUPLICATE — claim was released.
        assert r2.status_code == 200
        assert r2.json()["status"] == "processed"
