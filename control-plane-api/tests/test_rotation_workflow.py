"""
Tests for Certificate Rotation Workflow with Grace Period (CAB-869)
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.events import CertificateRotatedEvent, GracePeriodExpiredEvent, _EVENT_TYPE_MAP
from src.models.client import Client, ClientStatus


# =============================================================================
# Model tests
# =============================================================================


class TestClientGracePeriod:
    """Tests for Client model grace period fields and property."""

    def test_is_in_grace_period_true(self):
        client = Client(
            tenant_id="t1",
            name="test",
            certificate_cn="test",
            status=ClientStatus.ACTIVE,
        )
        client.previous_cert_expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        assert client.is_in_grace_period is True

    def test_is_in_grace_period_false_expired(self):
        client = Client(
            tenant_id="t1",
            name="test",
            certificate_cn="test",
            status=ClientStatus.ACTIVE,
        )
        client.previous_cert_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert client.is_in_grace_period is False

    def test_is_in_grace_period_false_no_previous(self):
        client = Client(
            tenant_id="t1",
            name="test",
            certificate_cn="test",
            status=ClientStatus.ACTIVE,
        )
        assert client.is_in_grace_period is False

    def test_rotation_count_default(self):
        client = Client(
            tenant_id="t1",
            name="test",
            certificate_cn="test",
            status=ClientStatus.ACTIVE,
            rotation_count=0,
        )
        assert client.rotation_count == 0


# =============================================================================
# Event tests
# =============================================================================


class TestRotationEvents:
    """Tests for rotation-related events."""

    def test_certificate_rotated_event_has_grace_expires_at(self):
        now = datetime.now(timezone.utc)
        grace = now + timedelta(hours=24)
        event = CertificateRotatedEvent(
            client_id="c1",
            tenant_id="t1",
            old_serial="old",
            new_serial="new",
            old_fingerprint="oldfp",
            new_fingerprint="newfp",
            rotated_at=now,
            grace_expires_at=grace,
        )
        assert event.grace_expires_at == grace

    def test_certificate_rotated_event_grace_optional(self):
        now = datetime.now(timezone.utc)
        event = CertificateRotatedEvent(
            client_id="c1",
            tenant_id="t1",
            old_serial="old",
            new_serial="new",
            old_fingerprint="oldfp",
            new_fingerprint="newfp",
            rotated_at=now,
        )
        assert event.grace_expires_at is None

    def test_grace_period_expired_event(self):
        now = datetime.now(timezone.utc)
        event = GracePeriodExpiredEvent(
            client_id="c1",
            tenant_id="t1",
            scheduled_at=now,
        )
        assert event.client_id == "c1"
        assert event.correlation_id  # auto-generated

    def test_event_type_map_includes_grace(self):
        assert "GracePeriodExpiredEvent" in _EVENT_TYPE_MAP
        assert _EVENT_TYPE_MAP["GracePeriodExpiredEvent"] == "GRACE_PERIOD_EXPIRED"


# =============================================================================
# Schema tests
# =============================================================================


class TestRotationSchemas:
    """Tests for rotation-related schema fields."""

    def test_rotate_request_default_grace(self):
        from src.schemas.client import CertificateRotateRequest
        req = CertificateRotateRequest()
        assert req.grace_period_hours is None
        assert req.reason == "rotation"

    def test_rotate_request_custom_grace(self):
        from src.schemas.client import CertificateRotateRequest
        req = CertificateRotateRequest(grace_period_hours=48)
        assert req.grace_period_hours == 48

    def test_rotate_request_grace_validation(self):
        from pydantic import ValidationError
        from src.schemas.client import CertificateRotateRequest
        with pytest.raises(ValidationError):
            CertificateRotateRequest(grace_period_hours=0)
        with pytest.raises(ValidationError):
            CertificateRotateRequest(grace_period_hours=200)

    def test_client_response_has_rotation_fields(self):
        from src.schemas.client import ClientResponse
        fields = ClientResponse.model_fields
        assert "certificate_fingerprint_previous" in fields
        assert "previous_cert_expires_at" in fields
        assert "is_in_grace_period" in fields
        assert "last_rotated_at" in fields
        assert "rotation_count" in fields

    def test_client_with_certificate_has_grace_period_ends(self):
        from src.schemas.client import ClientWithCertificate
        fields = ClientWithCertificate.model_fields
        assert "grace_period_ends" in fields


# =============================================================================
# Config tests
# =============================================================================


class TestRotationConfig:
    """Tests for rotation config defaults."""

    def test_default_grace_period_hours(self):
        from src.config import Settings
        s = Settings()
        assert s.CERTIFICATE_GRACE_PERIOD_HOURS == 24


# =============================================================================
# Grace period service tests
# =============================================================================


class TestGracePeriodService:
    """Tests for GracePeriodService."""

    def test_schedule_cleanup_emits_event(self):
        from src.services.grace_period_service import grace_period_service
        now = datetime.now(timezone.utc)
        with patch("src.services.grace_period_service.emit_event") as mock_emit:
            grace_period_service.schedule_cleanup(
                client_id="c1",
                tenant_id="t1",
                expires_at=now,
            )
            mock_emit.assert_called_once()
            event = mock_emit.call_args[0][0]
            assert isinstance(event, GracePeriodExpiredEvent)
            assert event.client_id == "c1"
            assert event.scheduled_at == now
