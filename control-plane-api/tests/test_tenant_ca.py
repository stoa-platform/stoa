"""Tests for Tenant CA API (CAB-1787).

Tests CA keypair generation, CSR signing, CA retrieval, and revocation.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.tenant import Tenant
from src.models.tenant_ca import TenantCA
from src.routers.tenant_ca import router
from src.services.tenant_ca_service import (
    CA_VALIDITY_DAYS,
    generate_ca_keypair,
    sign_csr,
)

# --- Helpers ---


def make_cpi_admin() -> User:
    return User(id="admin-1", email="admin@test.com", username="admin", roles=["cpi-admin"])


def make_tenant_admin(tenant_id: str = "acme") -> User:
    return User(
        id="ta-1",
        email="ta@test.com",
        username="tenant-admin",
        roles=["tenant-admin"],
        tenant_id=tenant_id,
    )


def make_viewer(tenant_id: str = "acme") -> User:
    return User(id="v-1", email="v@test.com", username="viewer", roles=["viewer"], tenant_id=tenant_id)


def make_tenant(tenant_id: str = "acme", name: str = "Acme Corp") -> MagicMock:
    t = MagicMock(spec=Tenant)
    t.id = tenant_id
    t.name = name
    return t


def make_tenant_ca_mock(tenant_id: str = "acme") -> MagicMock:
    ca = MagicMock(spec=TenantCA)
    ca.id = uuid.uuid4()
    ca.tenant_id = tenant_id
    ca.ca_certificate_pem = "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
    ca.encrypted_private_key = "encrypted-key-data"
    ca.subject_dn = f"CN={tenant_id}-ca,OU=Acme Corp,O=STOA Platform"
    ca.serial_number = "abc123"
    ca.not_before = datetime(2026, 1, 1, tzinfo=UTC)
    ca.not_after = datetime(2036, 1, 1, tzinfo=UTC)
    ca.key_algorithm = "RSA-4096"
    ca.fingerprint_sha256 = "a" * 64
    ca.status = "active"
    ca.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    return ca


def generate_test_csr() -> str:
    """Generate a valid CSR for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "test-consumer"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
                ]
            )
        )
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def _setup_overrides(app: FastAPI, user: User, mock_db: AsyncMock) -> None:
    """Configure FastAPI dependency overrides for tests."""
    app.dependency_overrides[get_current_user] = lambda: user

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db


# --- Unit tests for tenant_ca_service ---


class TestGenerateCAKeypair:
    def test_generates_valid_keypair(self):
        result = generate_ca_keypair("acme", "Acme Corp")

        assert result["key_algorithm"] == "RSA-4096"
        assert result["subject_dn"]
        assert "acme-ca" in result["subject_dn"]
        assert result["ca_certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
        assert result["encrypted_private_key"]
        assert len(result["fingerprint_sha256"]) == 64
        assert result["not_before"] < result["not_after"]

    def test_ca_certificate_is_self_signed(self):
        result = generate_ca_keypair("test-tenant", "Test Tenant")

        cert = x509.load_pem_x509_certificate(result["ca_certificate_pem"].encode())
        assert cert.subject == cert.issuer

    def test_ca_has_correct_extensions(self):
        result = generate_ca_keypair("test-tenant", "Test Tenant")

        cert = x509.load_pem_x509_certificate(result["ca_certificate_pem"].encode())

        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.value.ca is True
        assert bc.value.path_length == 0
        assert bc.critical is True

        ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.value.key_cert_sign is True
        assert ku.value.crl_sign is True

    def test_ca_validity_is_10_years(self):
        result = generate_ca_keypair("acme", "Acme Corp")

        delta = result["not_after"] - result["not_before"]
        assert abs(delta.days - CA_VALIDITY_DAYS) <= 1


class TestSignCSR:
    def test_signs_valid_csr(self):
        ca = generate_ca_keypair("acme", "Acme Corp")
        csr_pem = generate_test_csr()

        signed_pem = sign_csr(
            csr_pem=csr_pem,
            ca_cert_pem=ca["ca_certificate_pem"],
            encrypted_private_key=ca["encrypted_private_key"],
        )

        assert signed_pem.startswith("-----BEGIN CERTIFICATE-----")

        signed_cert = x509.load_pem_x509_certificate(signed_pem.encode())
        ca_cert = x509.load_pem_x509_certificate(ca["ca_certificate_pem"].encode())
        assert signed_cert.issuer == ca_cert.subject
        assert "test-consumer" in signed_cert.subject.rfc4514_string()

    def test_signed_cert_has_client_auth_eku(self):
        ca = generate_ca_keypair("acme", "Acme Corp")
        csr_pem = generate_test_csr()

        signed_pem = sign_csr(
            csr_pem=csr_pem,
            ca_cert_pem=ca["ca_certificate_pem"],
            encrypted_private_key=ca["encrypted_private_key"],
        )

        signed_cert = x509.load_pem_x509_certificate(signed_pem.encode())
        eku = signed_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        assert x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in eku.value

    def test_signed_cert_is_not_ca(self):
        ca = generate_ca_keypair("acme", "Acme Corp")
        csr_pem = generate_test_csr()

        signed_pem = sign_csr(
            csr_pem=csr_pem,
            ca_cert_pem=ca["ca_certificate_pem"],
            encrypted_private_key=ca["encrypted_private_key"],
        )

        signed_cert = x509.load_pem_x509_certificate(signed_pem.encode())
        bc = signed_cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.value.ca is False

    def test_custom_validity_days(self):
        ca = generate_ca_keypair("acme", "Acme Corp")
        csr_pem = generate_test_csr()

        signed_pem = sign_csr(
            csr_pem=csr_pem,
            ca_cert_pem=ca["ca_certificate_pem"],
            encrypted_private_key=ca["encrypted_private_key"],
            validity_days=30,
        )

        signed_cert = x509.load_pem_x509_certificate(signed_pem.encode())
        delta = signed_cert.not_valid_after_utc - signed_cert.not_valid_before_utc
        assert abs(delta.days - 30) <= 1

    def test_rejects_invalid_csr(self):
        ca = generate_ca_keypair("acme", "Acme Corp")

        with pytest.raises(ValueError, match="Invalid CSR"):
            sign_csr(
                csr_pem="not-a-csr",
                ca_cert_pem=ca["ca_certificate_pem"],
                encrypted_private_key=ca["encrypted_private_key"],
            )


# --- API endpoint tests ---


@pytest.fixture
def app():
    """Create a FastAPI app with the tenant_ca router."""
    test_app = FastAPI()
    test_app.include_router(router)
    yield test_app
    test_app.dependency_overrides.clear()


class TestGenerateEndpoint:
    @pytest.mark.asyncio
    async def test_generate_ca_success(self, app):
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=make_tenant())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/tenants/acme/ca/generate")

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == "acme"
        assert data["key_algorithm"] == "RSA-4096"
        assert data["status"] == "active"
        assert data["ca_certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")

    @pytest.mark.asyncio
    async def test_generate_ca_conflict(self, app):
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=make_tenant())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = make_tenant_ca_mock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/tenants/acme/ca/generate")

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_generate_ca_viewer_forbidden(self, app):
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=make_tenant())

        _setup_overrides(app, make_viewer(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/tenants/acme/ca/generate")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_ca_tenant_not_found(self, app):
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/tenants/nonexistent/ca/generate")

        assert response.status_code == 404


class TestGetCAEndpoint:
    @pytest.mark.asyncio
    async def test_get_ca_success(self, app):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = make_tenant_ca_mock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/tenants/acme/ca")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "acme"
        assert data["status"] == "active"
        assert "encrypted_private_key" not in data
        assert "private_key" not in data

    @pytest.mark.asyncio
    async def test_get_ca_not_found(self, app):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/tenants/acme/ca")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_ca_access_denied(self, app):
        user = User(
            id="other",
            email="other@test.com",
            username="other",
            roles=["viewer"],
            tenant_id="other-tenant",
        )
        mock_db = AsyncMock()
        _setup_overrides(app, user, mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/tenants/acme/ca")

        assert response.status_code == 403


class TestSignEndpoint:
    @pytest.mark.asyncio
    async def test_sign_csr_success(self, app):
        ca_data = generate_ca_keypair("acme", "Acme Corp")
        ca_mock = make_tenant_ca_mock()
        ca_mock.ca_certificate_pem = ca_data["ca_certificate_pem"]
        ca_mock.encrypted_private_key = ca_data["encrypted_private_key"]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ca_mock
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)
        csr_pem = generate_test_csr()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/tenants/acme/ca/sign",
                json={"csr_pem": csr_pem, "validity_days": 90},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["signed_certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
        assert "test-consumer" in data["subject_dn"]
        assert data["validity_days"] == 90

    @pytest.mark.asyncio
    async def test_sign_invalid_csr(self, app):
        ca_data = generate_ca_keypair("acme", "Acme Corp")
        ca_mock = make_tenant_ca_mock()
        ca_mock.ca_certificate_pem = ca_data["ca_certificate_pem"]
        ca_mock.encrypted_private_key = ca_data["encrypted_private_key"]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ca_mock
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/tenants/acme/ca/sign",
                json={"csr_pem": "not-valid-csr"},
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_sign_no_active_ca(self, app):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/tenants/acme/ca/sign",
                json={"csr_pem": generate_test_csr()},
            )

        assert response.status_code == 404


class TestRevokeEndpoint:
    @pytest.mark.asyncio
    async def test_revoke_ca_success(self, app):
        ca_mock = make_tenant_ca_mock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ca_mock
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/v1/tenants/acme/ca")

        assert response.status_code == 200
        assert ca_mock.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_ca_non_admin_forbidden(self, app):
        mock_db = AsyncMock()
        _setup_overrides(app, make_tenant_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/v1/tenants/acme/ca")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_revoke_ca_not_found(self, app):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        _setup_overrides(app, make_cpi_admin(), mock_db)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/v1/tenants/acme/ca")

        assert response.status_code == 404
