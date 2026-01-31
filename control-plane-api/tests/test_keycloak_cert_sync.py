"""
Tests for CAB-866: Keycloak Certificate Sync

Covers:
- Sync service: create, rotate, revoke
- Fingerprint format (base64url, no padding)
- Consumer retry logic + DLQ
- correlation_id traceability
"""
import base64
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.events import ClientCreatedEvent, CertificateRotatedEvent, ClientRevokedEvent
from src.models.client import Client, ClientStatus
from src.services.keycloak_cert_sync_service import (
    KeycloakCertSyncService,
    hex_to_base64url,
)
from src.services.kafka_cert_consumer import CertificateEventConsumer, MAX_RETRIES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_client(**overrides) -> Client:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "name": "my-service",
        "certificate_cn": "my-service.acme.gostoa.dev",
        "certificate_serial": "1234567890ABCDEF",
        "certificate_fingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "certificate_pem": "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----",
        "certificate_not_before": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "certificate_not_after": datetime(2027, 1, 1, tzinfo=timezone.utc),
        "status": ClientStatus.ACTIVE,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    client = Client.__new__(Client)
    for k, v in defaults.items():
        setattr(client, k, v)
    return client


# ---------------------------------------------------------------------------
# hex_to_base64url
# ---------------------------------------------------------------------------

class TestHexToBase64url:
    def test_known_value(self):
        # 32 zero bytes → base64url with no padding
        hex_str = "00" * 32
        result = hex_to_base64url(hex_str)
        assert result == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

    def test_no_padding(self):
        result = hex_to_base64url("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")
        assert "=" not in result

    def test_url_safe_chars(self):
        # Use bytes that would produce + and / in standard base64
        hex_str = "fb" * 32  # high-bit bytes
        result = hex_to_base64url(hex_str)
        assert "+" not in result
        assert "/" not in result

    def test_roundtrip(self):
        hex_str = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        b64url = hex_to_base64url(hex_str)
        # Pad back and decode
        padded = b64url + "=" * (4 - len(b64url) % 4) if len(b64url) % 4 else b64url
        decoded = base64.urlsafe_b64decode(padded)
        assert decoded == bytes.fromhex(hex_str)

    def test_colon_separated_input(self):
        hex_with_colons = "a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2:c3:d4:e5:f6:a1:b2"
        result = hex_to_base64url(hex_with_colons)
        assert "=" not in result
        assert len(result) > 0


# ---------------------------------------------------------------------------
# KeycloakCertSyncService
# ---------------------------------------------------------------------------

class TestKeycloakCertSyncService:
    @pytest.fixture
    def svc(self):
        return KeycloakCertSyncService()

    @pytest.fixture
    def client(self):
        return _make_client()

    @pytest.mark.asyncio
    @patch("src.services.keycloak_cert_sync_service.keycloak_service")
    async def test_sync_creates_keycloak_client(self, mock_kc, svc, client):
        mock_kc.get_client = AsyncMock(return_value=None)
        mock_kc._admin = MagicMock()
        mock_kc._admin.create_client = MagicMock()

        # After creation, get_client returns the created client
        created = {"id": "kc-uuid-123", "clientId": f"mtls-{client.tenant_id}-{client.certificate_cn}"}
        mock_kc.get_client = AsyncMock(side_effect=[None, created])

        correlation_id = str(uuid.uuid4())
        result = await svc.sync_client_certificate(client, correlation_id)

        assert result["action"] == "created"
        assert result["keycloak_uuid"] == "kc-uuid-123"

        # Verify create_client was called with correct attributes
        call_args = mock_kc._admin.create_client.call_args[0][0]
        assert call_args["clientAuthenticatorType"] == "client-x509"
        assert "x509.certificate.sha256" in call_args["attributes"]
        assert call_args["attributes"]["stoa.tenant"] == "acme"

        # Verify fingerprint is base64url
        fp = call_args["attributes"]["x509.certificate.sha256"]
        assert "=" not in fp
        assert "+" not in fp
        assert "/" not in fp

        # Verify protocol mappers
        mapper_names = [m["name"] for m in call_args["protocolMappers"]]
        assert "cnf-certificate-binding" in mapper_names
        assert "tenant-mapper" in mapper_names

        # Verify cnf claim value
        cnf_mapper = next(m for m in call_args["protocolMappers"] if m["name"] == "cnf-certificate-binding")
        cnf_value = json.loads(cnf_mapper["config"]["claim.value"])
        assert "x5t#S256" in cnf_value

    @pytest.mark.asyncio
    @patch("src.services.keycloak_cert_sync_service.keycloak_service")
    async def test_sync_updates_existing_client(self, mock_kc, svc, client):
        existing = {"id": "kc-uuid-456", "clientId": f"mtls-acme-{client.certificate_cn}"}
        mock_kc.get_client = AsyncMock(return_value=existing)
        mock_kc.update_client = AsyncMock(return_value=True)

        result = await svc.sync_client_certificate(client, "corr-123")

        assert result["action"] == "updated"
        mock_kc.update_client.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.keycloak_cert_sync_service.keycloak_service")
    async def test_rotate_sets_previous_fingerprint(self, mock_kc, svc, client):
        existing = {"id": "kc-uuid-789", "clientId": f"mtls-acme-{client.certificate_cn}"}
        mock_kc.get_client = AsyncMock(return_value=existing)
        mock_kc.update_client = AsyncMock(return_value=True)

        old_fp = "bb" * 32
        result = await svc.rotate_client_certificate(client, old_fp, "corr-456")

        assert result["action"] == "rotated"
        call_args = mock_kc.update_client.call_args[0][1]
        assert "x509.certificate.sha256.previous" in call_args["attributes"]

    @pytest.mark.asyncio
    @patch("src.services.keycloak_cert_sync_service.keycloak_service")
    async def test_revoke_disables_client(self, mock_kc, svc, client):
        existing = {"id": "kc-uuid-abc", "clientId": f"mtls-acme-{client.certificate_cn}"}
        mock_kc.get_client = AsyncMock(return_value=existing)
        mock_kc.update_client = AsyncMock(return_value=True)

        result = await svc.revoke_client_certificate(client, "corr-789")

        assert result["action"] == "revoked"
        mock_kc.update_client.assert_called_once_with("kc-uuid-abc", {"enabled": False})

    @pytest.mark.asyncio
    @patch("src.services.keycloak_cert_sync_service.keycloak_service")
    async def test_revoke_missing_client_is_noop(self, mock_kc, svc, client):
        mock_kc.get_client = AsyncMock(return_value=None)

        result = await svc.revoke_client_certificate(client, "corr-000")

        assert result["action"] == "noop"


# ---------------------------------------------------------------------------
# CertificateEventConsumer — retry & DLQ
# ---------------------------------------------------------------------------

class TestCertificateEventConsumer:
    @pytest.fixture
    def consumer(self):
        return CertificateEventConsumer()

    @pytest.mark.asyncio
    @patch("src.services.kafka_cert_consumer.keycloak_cert_sync_service")
    @patch("src.services.kafka_cert_consumer.async_session")
    async def test_successful_event_no_retry(self, mock_session_ctx, mock_sync_svc, consumer):
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=client)
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_sync_svc.sync_client_certificate = AsyncMock(return_value={"action": "created"})

        event = {
            "type": "CLIENT_CREATED",
            "correlation_id": "corr-ok",
            "tenant_id": "acme",
            "payload": {"client_id": str(client.id)},
        }
        # Should not raise
        await consumer._process_with_retry(event)
        mock_sync_svc.sync_client_certificate.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.kafka_cert_consumer.kafka_service")
    @patch("src.services.kafka_cert_consumer.keycloak_cert_sync_service")
    @patch("src.services.kafka_cert_consumer.async_session")
    async def test_retry_then_dlq(self, mock_session_ctx, mock_sync_svc, mock_kafka, consumer):
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=client)
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_sync_svc.sync_client_certificate = AsyncMock(side_effect=RuntimeError("Keycloak down"))
        mock_kafka.publish = AsyncMock()

        event = {
            "type": "CLIENT_CREATED",
            "correlation_id": "corr-fail",
            "tenant_id": "acme",
            "payload": {"client_id": str(client.id)},
        }

        # Patch sleep to avoid real delays
        with patch("src.services.kafka_cert_consumer.asyncio.sleep", new_callable=AsyncMock):
            await consumer._process_with_retry(event)

        # sync was attempted MAX_RETRIES times
        assert mock_sync_svc.sync_client_certificate.call_count == MAX_RETRIES

        # DLQ publish was called
        mock_kafka.publish.assert_called_once()
        dlq_call = mock_kafka.publish.call_args
        assert dlq_call.kwargs["topic"] == "cert-events-dlq"

    @pytest.mark.asyncio
    @patch("src.services.kafka_cert_consumer.keycloak_cert_sync_service")
    @patch("src.services.kafka_cert_consumer.async_session")
    async def test_retry_succeeds_on_third_attempt(self, mock_session_ctx, mock_sync_svc, consumer):
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=client)
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        # Fail twice, succeed on third
        mock_sync_svc.sync_client_certificate = AsyncMock(
            side_effect=[RuntimeError("fail"), RuntimeError("fail"), {"action": "created"}]
        )

        event = {
            "type": "CLIENT_CREATED",
            "correlation_id": "corr-retry-ok",
            "tenant_id": "acme",
            "payload": {"client_id": str(client.id)},
        }

        with patch("src.services.kafka_cert_consumer.asyncio.sleep", new_callable=AsyncMock):
            await consumer._process_with_retry(event)

        assert mock_sync_svc.sync_client_certificate.call_count == 3


# ---------------------------------------------------------------------------
# Event dataclasses — correlation_id
# ---------------------------------------------------------------------------

class TestEventCorrelationId:
    def test_client_created_has_correlation_id(self):
        event = ClientCreatedEvent(
            client_id="c1", tenant_id="t1", common_name="cn",
            certificate_serial="s1", certificate_fingerprint="aa" * 32,
            created_at=datetime.now(timezone.utc),
        )
        assert event.correlation_id  # auto-generated UUID
        uuid.UUID(event.correlation_id)  # validates format

    def test_rotated_event_has_correlation_id(self):
        event = CertificateRotatedEvent(
            client_id="c1", tenant_id="t1",
            old_serial="s1", new_serial="s2",
            old_fingerprint="aa" * 32, new_fingerprint="bb" * 32,
            rotated_at=datetime.now(timezone.utc),
        )
        assert event.correlation_id

    def test_revoked_event_has_correlation_id(self):
        event = ClientRevokedEvent(
            client_id="c1", tenant_id="t1",
            certificate_serial="s1", reason="key_compromise",
            revoked_at=datetime.now(timezone.utc),
        )
        assert event.correlation_id

    def test_custom_correlation_id(self):
        cid = "my-custom-corr-id"
        event = ClientCreatedEvent(
            client_id="c1", tenant_id="t1", common_name="cn",
            certificate_serial="s1", certificate_fingerprint="aa" * 32,
            created_at=datetime.now(timezone.utc),
            correlation_id=cid,
        )
        assert event.correlation_id == cid
