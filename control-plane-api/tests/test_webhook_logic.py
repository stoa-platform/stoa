"""Tests for WebhookService pure logic methods (CAB-1291)"""
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.services.webhook_service import (
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAYS,
    WebhookService,
)


def _mock_subscription(**overrides):
    sub = MagicMock()
    defaults = {
        "id": "sub-1",
        "application_id": "app-1",
        "application_name": "My App",
        "api_id": "api-1",
        "api_name": "Weather API",
        "tenant_id": "acme",
        "subscriber_id": "user-1",
        "subscriber_email": "user@example.com",
        "status": MagicMock(value="approved"),
        "approved_by": "admin",
        "approved_at": datetime(2026, 2, 15, 10, 0, 0),
        "revoked_by": None,
        "revoked_at": None,
        "status_reason": None,
        "rotation_count": 0,
        "last_rotated_at": None,
        "previous_key_expires_at": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(sub, k, v)
    return sub


def _mock_deployment(**overrides):
    dep = MagicMock()
    defaults = {
        "id": "dep-1",
        "api_id": "api-1",
        "api_name": "Weather API",
        "tenant_id": "acme",
        "environment": "staging",
        "version": "1.2.0",
        "status": "in_progress",
        "deployed_by": "alice",
        "error_message": None,
        "rollback_of": None,
        "rollback_version": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(dep, k, v)
    return dep


class TestConstants:
    def test_retry_delays(self):
        assert len(RETRY_DELAYS) == MAX_RETRY_ATTEMPTS
        assert RETRY_DELAYS[0] == 60
        assert RETRY_DELAYS[-1] == 7200

    def test_max_attempts(self):
        assert MAX_RETRY_ATTEMPTS == 5


class TestBuildPayload:
    def _svc(self):
        return WebhookService(db=MagicMock())

    def test_basic_payload(self):
        svc = self._svc()
        sub = _mock_subscription()
        payload = svc._build_payload("subscription.created", sub)
        assert payload["event"] == "subscription.created"
        assert "timestamp" in payload
        assert payload["data"]["subscription_id"] == "sub-1"
        assert payload["data"]["tenant_id"] == "acme"
        assert payload["data"]["api_name"] == "Weather API"

    def test_approved_event(self):
        svc = self._svc()
        sub = _mock_subscription()
        payload = svc._build_payload("subscription.approved", sub)
        assert payload["data"]["approved_by"] == "admin"
        assert "approved_at" in payload["data"]

    def test_revoked_event(self):
        svc = self._svc()
        sub = _mock_subscription(
            revoked_by="admin",
            revoked_at=datetime(2026, 2, 16),
            status_reason="policy violation",
        )
        payload = svc._build_payload("subscription.revoked", sub)
        assert payload["data"]["revoked_by"] == "admin"
        assert payload["data"]["reason"] == "policy violation"

    def test_key_rotated_event(self):
        svc = self._svc()
        sub = _mock_subscription(
            rotation_count=3,
            last_rotated_at=datetime(2026, 2, 16),
            previous_key_expires_at=datetime(2026, 2, 17),
        )
        payload = svc._build_payload("subscription.key_rotated", sub)
        assert payload["data"]["rotation_count"] == 3
        assert payload["data"]["last_rotated_at"] is not None

    def test_additional_data_merged(self):
        svc = self._svc()
        sub = _mock_subscription()
        payload = svc._build_payload("subscription.created", sub, {"extra_key": "val"})
        assert payload["data"]["extra_key"] == "val"

    def test_status_without_value_attr(self):
        svc = self._svc()
        sub = _mock_subscription(status="approved")  # plain string, no .value
        payload = svc._build_payload("subscription.created", sub)
        assert payload["data"]["status"] == "approved"


class TestBuildDeploymentPayload:
    def _svc(self):
        return WebhookService(db=MagicMock())

    def test_basic(self):
        svc = self._svc()
        dep = _mock_deployment()
        payload = svc._build_deployment_payload("deployment.started", dep)
        assert payload["event"] == "deployment.started"
        assert payload["data"]["deployment_id"] == "dep-1"
        assert payload["data"]["version"] == "1.2.0"

    def test_failed_event(self):
        svc = self._svc()
        dep = _mock_deployment(error_message="timeout")
        payload = svc._build_deployment_payload("deployment.failed", dep)
        assert payload["data"]["error_message"] == "timeout"

    def test_rolled_back_event(self):
        svc = self._svc()
        dep = _mock_deployment(rollback_of="dep-0", rollback_version="1.1.0")
        payload = svc._build_deployment_payload("deployment.rolled_back", dep)
        assert payload["data"]["rollback_of"] == "dep-0"
        assert payload["data"]["rollback_version"] == "1.1.0"

    def test_additional_data(self):
        svc = self._svc()
        dep = _mock_deployment()
        payload = svc._build_deployment_payload("deployment.started", dep, {"note": "manual"})
        assert payload["data"]["note"] == "manual"


class TestGenerateSignature:
    def _svc(self):
        return WebhookService(db=MagicMock())

    def test_produces_sha256_prefix(self):
        svc = self._svc()
        sig = svc._generate_signature("secret", {"key": "value"})
        assert sig.startswith("sha256=")

    def test_deterministic(self):
        svc = self._svc()
        payload = {"a": 1, "b": 2}
        sig1 = svc._generate_signature("secret", payload)
        sig2 = svc._generate_signature("secret", payload)
        assert sig1 == sig2

    def test_different_secret_different_sig(self):
        svc = self._svc()
        payload = {"a": 1}
        sig1 = svc._generate_signature("secret1", payload)
        sig2 = svc._generate_signature("secret2", payload)
        assert sig1 != sig2

    def test_uses_sorted_keys(self):
        svc = self._svc()
        payload = {"b": 2, "a": 1}
        sig = svc._generate_signature("s", payload)
        # Verify by computing manually with sorted keys
        expected_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        import hashlib
        import hmac as hmac_mod
        expected = "sha256=" + hmac_mod.new(b"s", expected_bytes, hashlib.sha256).hexdigest()
        assert sig == expected
