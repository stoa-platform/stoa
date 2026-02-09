"""Tests for mTLS bulk onboarding, revocation, and rotation (CAB-864 Phase 3)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.consumer import CertificateStatus, Consumer, ConsumerStatus
from src.services.certificate_utils import CertificateInfo, parse_pem_certificate

TENANT_ID = "oasis"
OTHER_TENANT = "other-tenant"
USER_ID = "user-123"
USER_EMAIL = "admin@oasis.test"


def _make_user(tenant_id: str = TENANT_ID, roles: list[str] | None = None):
    user = MagicMock()
    user.id = USER_ID
    user.email = USER_EMAIL
    user.tenant_id = tenant_id
    user.roles = roles or ["tenant-admin"]
    return user


def _make_consumer(
    tenant_id: str = TENANT_ID,
    external_id: str = "acme-001",
    with_cert: bool = False,
    cert_status: str = "active",
) -> Consumer:
    consumer = Consumer(
        id=uuid.uuid4(),
        external_id=external_id,
        name="ACME Corp",
        email="api@acme.test",
        company="ACME",
        tenant_id=tenant_id,
        status=ConsumerStatus.ACTIVE,
        created_by=USER_ID,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    if with_cert:
        consumer.certificate_fingerprint = "a" * 64
        consumer.certificate_subject_dn = "CN=acme.test"
        consumer.certificate_issuer_dn = "CN=ca.test"
        consumer.certificate_serial = "deadbeef"
        consumer.certificate_not_before = datetime.now(UTC) - timedelta(days=30)
        consumer.certificate_not_after = datetime.now(UTC) + timedelta(days=335)
        consumer.certificate_pem = "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
        consumer.certificate_status = cert_status
        consumer.rotation_count = 0
    return consumer


def _make_cert_info(fingerprint_hex: str = "b" * 64, expired: bool = False) -> CertificateInfo:
    not_after = (
        datetime.now(UTC) - timedelta(days=1) if expired else datetime.now(UTC) + timedelta(days=365)
    )
    return CertificateInfo(
        fingerprint_hex=fingerprint_hex,
        fingerprint_b64url="bbbbb",
        subject_dn="CN=new.test",
        issuer_dn="CN=ca.test",
        serial="cafe01",
        not_before=datetime.now(UTC) - timedelta(days=1),
        not_after=not_after,
        pem="-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----",
    )


def _csv_bytes(rows: list[dict], fields: list[str] | None = None) -> bytes:
    if not fields:
        fields = list(rows[0].keys()) if rows else ["external_id", "name", "email"]
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(str(row.get(f, "")) for f in fields))
    return "\n".join(lines).encode("utf-8")


class TestCertificateUtils:
    def test_parse_empty_pem_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_pem_certificate("")

    def test_parse_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_pem_certificate("   \n\t  ")

    def test_parse_invalid_pem_raises(self):
        with pytest.raises(ValueError, match="Invalid PEM"):
            parse_pem_certificate(
                "-----BEGIN CERTIFICATE-----\nnot-base64\n-----END CERTIFICATE-----"
            )

    def test_parse_not_pem_raises(self):
        with pytest.raises(ValueError, match="Invalid PEM"):
            parse_pem_certificate("just some random text")


class TestBulkCreateConsumers:
    @pytest.mark.asyncio
    async def test_bulk_create_without_certs(self):
        csv_data = _csv_bytes([
            {"external_id": "p1", "name": "Partner 1", "email": "p1@test.com"},
            {"external_id": "p2", "name": "Partner 2", "email": "p2@test.com"},
        ])
        mock_repo = AsyncMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=None)
        created = _make_consumer(external_id="p1")
        mock_repo.create = AsyncMock(return_value=created)
        mock_repo.update = AsyncMock(return_value=created)
        mock_kc = AsyncMock()
        mock_kc.create_consumer_client = AsyncMock(
            return_value={"client_id": "oasis-p1", "client_secret": "secret"}
        )
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", mock_kc),
            patch("src.routers.consumers.get_current_user", return_value=_make_user()),
            patch("src.routers.consumers.get_db", return_value=AsyncMock()),
        ):
            from src.routers.consumers import bulk_create_consumers
            mock_db = AsyncMock(spec=AsyncSession)
            mock_db.commit = AsyncMock()
            result = await bulk_create_consumers(
                tenant_id=TENANT_ID,
                file=MagicMock(read=AsyncMock(return_value=csv_data)),
                user=_make_user(),
                db=mock_db,
            )
        assert result.total == 2
        assert result.success == 2
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_bulk_duplicate_external_id(self):
        csv_data = _csv_bytes([
            {"external_id": "exists", "name": "Dup", "email": "dup@test.com"},
        ])
        mock_repo = AsyncMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=_make_consumer())
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
            patch("src.routers.consumers.get_current_user", return_value=_make_user()),
        ):
            from src.routers.consumers import bulk_create_consumers
            mock_db = AsyncMock(spec=AsyncSession)
            mock_db.commit = AsyncMock()
            result = await bulk_create_consumers(
                tenant_id=TENANT_ID,
                file=MagicMock(read=AsyncMock(return_value=csv_data)),
                user=_make_user(),
                db=mock_db,
            )
        assert result.total == 1
        assert result.failed == 1
        assert "already exists" in result.results[0].error

    @pytest.mark.asyncio
    async def test_bulk_exceeds_max_rows(self):
        rows = [
            {"external_id": f"p{i}", "name": f"P{i}", "email": f"p{i}@test.com"}
            for i in range(101)
        ]
        csv_data = _csv_bytes(rows)
        with (
            patch("src.routers.consumers.ConsumerRepository"),
            patch("src.routers.consumers.keycloak_service"),
        ):
            from src.routers.consumers import bulk_create_consumers
            with pytest.raises(Exception) as exc_info:
                await bulk_create_consumers(
                    tenant_id=TENANT_ID,
                    file=MagicMock(read=AsyncMock(return_value=csv_data)),
                    user=_make_user(),
                    db=AsyncMock(spec=AsyncSession),
                )
            assert "100" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_bulk_missing_csv_columns(self):
        csv_data = b"name,email\nFoo,foo@bar.com\n"
        with (
            patch("src.routers.consumers.ConsumerRepository"),
            patch("src.routers.consumers.keycloak_service"),
        ):
            from src.routers.consumers import bulk_create_consumers
            with pytest.raises(Exception) as exc_info:
                await bulk_create_consumers(
                    tenant_id=TENANT_ID,
                    file=MagicMock(read=AsyncMock(return_value=csv_data)),
                    user=_make_user(),
                    db=AsyncMock(spec=AsyncSession),
                )
            assert "external_id" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_bulk_empty_csv(self):
        csv_data = b"external_id,name,email\n"
        with (
            patch("src.routers.consumers.ConsumerRepository"),
            patch("src.routers.consumers.keycloak_service"),
        ):
            from src.routers.consumers import bulk_create_consumers
            with pytest.raises(Exception) as exc_info:
                await bulk_create_consumers(
                    tenant_id=TENANT_ID,
                    file=MagicMock(read=AsyncMock(return_value=csv_data)),
                    user=_make_user(),
                    db=AsyncMock(spec=AsyncSession),
                )
            assert "no data" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_bulk_wrong_tenant_403(self):
        user = _make_user(tenant_id="wrong-tenant")
        csv_data = _csv_bytes([
            {"external_id": "p1", "name": "P1", "email": "p1@test.com"},
        ])
        with (
            patch("src.routers.consumers.ConsumerRepository"),
            patch("src.routers.consumers.keycloak_service"),
        ):
            from src.routers.consumers import bulk_create_consumers
            with pytest.raises(Exception) as exc_info:
                await bulk_create_consumers(
                    tenant_id=TENANT_ID,
                    file=MagicMock(read=AsyncMock(return_value=csv_data)),
                    user=user,
                    db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_with_cert_duplicate_fingerprint(self):
        csv_data = _csv_bytes(
            [{"external_id": "p1", "name": "P1", "email": "p1@test.com", "certificate_pem": "PEM"}],
            fields=["external_id", "name", "email", "certificate_pem"],
        )
        mock_repo = AsyncMock()
        mock_repo.get_by_external_id = AsyncMock(return_value=None)
        mock_repo.get_by_fingerprint = AsyncMock(return_value=_make_consumer(with_cert=True))
        cert_info = _make_cert_info()
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
            patch("src.routers.consumers.parse_pem_certificate", return_value=cert_info),
            patch("src.routers.consumers.validate_certificate_not_expired"),
        ):
            from src.routers.consumers import bulk_create_consumers
            mock_db = AsyncMock(spec=AsyncSession)
            mock_db.commit = AsyncMock()
            result = await bulk_create_consumers(
                tenant_id=TENANT_ID,
                file=MagicMock(read=AsyncMock(return_value=csv_data)),
                user=_make_user(),
                db=mock_db,
            )
        assert result.failed == 1
        assert "fingerprint" in result.results[0].error.lower()


class TestRevokeCertificate:
    @pytest.mark.asyncio
    async def test_revoke_active_certificate(self):
        consumer = _make_consumer(with_cert=True, cert_status="active")
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.update = AsyncMock(return_value=consumer)
        mock_kc = AsyncMock()
        mock_kc.disable_consumer_client = AsyncMock(return_value=True)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", mock_kc),
        ):
            from src.routers.consumers import revoke_certificate
            mock_db = AsyncMock(spec=AsyncSession)
            mock_db.commit = AsyncMock()
            await revoke_certificate(
                tenant_id=TENANT_ID, consumer_id=consumer.id, user=_make_user(), db=mock_db,
            )
        assert consumer.certificate_status == CertificateStatus.REVOKED
        assert consumer.certificate_fingerprint_previous is None
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_idempotent(self):
        consumer = _make_consumer(with_cert=True, cert_status=CertificateStatus.REVOKED)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import revoke_certificate
            mock_db = AsyncMock(spec=AsyncSession)
            await revoke_certificate(
                tenant_id=TENANT_ID, consumer_id=consumer.id, user=_make_user(), db=mock_db,
            )
        mock_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_no_certificate_400(self):
        consumer = _make_consumer(with_cert=False)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import revoke_certificate
            with pytest.raises(Exception) as exc_info:
                await revoke_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id, user=_make_user(),
                    db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_wrong_tenant_404(self):
        consumer = _make_consumer(tenant_id=OTHER_TENANT, with_cert=True)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import revoke_certificate
            with pytest.raises(Exception) as exc_info:
                await revoke_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id, user=_make_user(),
                    db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 404


class TestRotateCertificate:
    @pytest.mark.asyncio
    async def test_rotate_success(self):
        consumer = _make_consumer(with_cert=True)
        old_fp = consumer.certificate_fingerprint
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.get_by_fingerprint = AsyncMock(return_value=None)
        mock_repo.update = AsyncMock(return_value=consumer)
        cert_info = _make_cert_info()
        mock_kc = AsyncMock()
        mock_kc.update_consumer_client_cnf = AsyncMock(return_value=True)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", mock_kc),
            patch("src.routers.consumers.parse_pem_certificate", return_value=cert_info),
            patch("src.routers.consumers.validate_certificate_not_expired"),
        ):
            from src.routers.consumers import rotate_certificate
            from src.schemas.consumer import CertificateRotateRequest
            mock_db = AsyncMock(spec=AsyncSession)
            mock_db.commit = AsyncMock()
            request = CertificateRotateRequest(
                certificate_pem="-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----",
                grace_period_hours=48,
            )
            await rotate_certificate(
                tenant_id=TENANT_ID, consumer_id=consumer.id, request=request,
                user=_make_user(), db=mock_db,
            )
        assert consumer.certificate_fingerprint == cert_info.fingerprint_hex
        assert consumer.certificate_fingerprint_previous == old_fp
        assert consumer.certificate_status == CertificateStatus.ROTATING
        assert consumer.rotation_count == 1

    @pytest.mark.asyncio
    async def test_rotate_no_certificate_400(self):
        consumer = _make_consumer(with_cert=False)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import rotate_certificate
            from src.schemas.consumer import CertificateRotateRequest
            with pytest.raises(Exception) as exc_info:
                await rotate_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id,
                    request=CertificateRotateRequest(certificate_pem="PEM"),
                    user=_make_user(), db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rotate_revoked_certificate_400(self):
        consumer = _make_consumer(with_cert=True, cert_status=CertificateStatus.REVOKED)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import rotate_certificate
            from src.schemas.consumer import CertificateRotateRequest
            with pytest.raises(Exception) as exc_info:
                await rotate_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id,
                    request=CertificateRotateRequest(certificate_pem="PEM"),
                    user=_make_user(), db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 400
            assert "revoked" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_rotate_duplicate_fingerprint_409(self):
        consumer = _make_consumer(with_cert=True)
        other_consumer = _make_consumer(external_id="other")
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        mock_repo.get_by_fingerprint = AsyncMock(return_value=other_consumer)
        cert_info = _make_cert_info()
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
            patch("src.routers.consumers.parse_pem_certificate", return_value=cert_info),
            patch("src.routers.consumers.validate_certificate_not_expired"),
        ):
            from src.routers.consumers import rotate_certificate
            from src.schemas.consumer import CertificateRotateRequest
            with pytest.raises(Exception) as exc_info:
                await rotate_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id,
                    request=CertificateRotateRequest(certificate_pem="PEM"),
                    user=_make_user(), db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rotate_wrong_tenant_404(self):
        consumer = _make_consumer(tenant_id=OTHER_TENANT, with_cert=True)
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=consumer)
        with (
            patch("src.routers.consumers.ConsumerRepository", return_value=mock_repo),
            patch("src.routers.consumers.keycloak_service", AsyncMock()),
        ):
            from src.routers.consumers import rotate_certificate
            from src.schemas.consumer import CertificateRotateRequest
            with pytest.raises(Exception) as exc_info:
                await rotate_certificate(
                    tenant_id=TENANT_ID, consumer_id=consumer.id,
                    request=CertificateRotateRequest(certificate_pem="PEM"),
                    user=_make_user(), db=AsyncMock(spec=AsyncSession),
                )
            assert exc_info.value.status_code == 404
