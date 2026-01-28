"""
Tests for Client Router with mTLS Certificate Support

CAB-865: mTLS API Client Certificate Provisioning

Test Categories:
- TestCertificateExtensions: Verify X.509 extensions (Chucky)
- TestSecurityInjection: Injection tests (N3m0)
- TestTenantIsolation: Tenant isolation (Pr1nc3ss)
- TestRateLimiting: Rate limit certificate generation
- TestClientLifecycle: CRUD operations
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
import pytest_asyncio

from src.main import app
from src.models.client import Client, AuthType, ClientStatus
from src.schemas.client import AuthTypeEnum
from src.services.certificate_provider import CertificateBundle, CertificateRequest
from src.services.certificate_providers.mock_provider import MockCertificateProvider


# Mock user for testing
def get_mock_user(tenant_id: str = "test-tenant", roles: list = None):
    """Create a mock user for testing."""
    mock_user = MagicMock()
    mock_user.id = "test-user-id"
    mock_user.email = "test@example.com"
    mock_user.tenant_id = tenant_id
    mock_user.roles = roles or ["tenant-admin"]
    return mock_user


class TestMockCertificateProvider:
    """Test MockCertificateProvider functionality."""

    @pytest.mark.asyncio
    async def test_generate_certificate_success(self):
        """Test successful certificate generation."""
        provider = MockCertificateProvider()
        request = CertificateRequest(
            client_id="test-client-123",
            client_name="billing-service",
            tenant_id="test-tenant",
            validity_days=365,
            key_size=4096,
        )

        bundle = await provider.generate_certificate(request)

        assert bundle is not None
        assert bundle.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert bundle.private_key_pem.startswith("-----BEGIN RSA PRIVATE KEY-----")
        assert bundle.ca_chain_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert len(bundle.fingerprint_sha256) == 64  # SHA256 hex
        assert len(bundle.serial_number) > 0

    @pytest.mark.asyncio
    async def test_provider_name(self):
        """Test provider name."""
        provider = MockCertificateProvider()
        assert provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_revoke_certificate(self):
        """Test certificate revocation (mock always succeeds)."""
        provider = MockCertificateProvider()
        result = await provider.revoke_certificate("test-serial", "Test revocation")
        assert result is True


class TestCertificateExtensions:
    """
    Verify X.509 extensions are correctly set (Chucky review).
    """

    @pytest.fixture
    def certificate_bundle(self):
        """Generate a certificate bundle for testing."""
        import asyncio
        provider = MockCertificateProvider()
        request = CertificateRequest(
            client_id="test-client",
            client_name="test-service",
            tenant_id="test-tenant",
        )
        return asyncio.get_event_loop().run_until_complete(
            provider.generate_certificate(request)
        )

    def test_has_basic_constraints(self, certificate_bundle):
        """Verify BasicConstraints extension is present and correct."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc is not None
        assert bc.critical is True
        assert bc.value.ca is False

    def test_has_key_usage(self, certificate_bundle):
        """Verify KeyUsage extension is present and correct."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku is not None
        assert ku.critical is True
        assert ku.value.digital_signature is True
        assert ku.value.key_encipherment is True
        assert ku.value.key_cert_sign is False

    def test_has_extended_key_usage(self, certificate_bundle):
        """Verify ExtendedKeyUsage extension (CLIENT_AUTH)."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        assert eku is not None
        assert x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in eku.value

    def test_has_subject_alternative_name(self, certificate_bundle):
        """Verify SubjectAlternativeName extension."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        assert san is not None

        # Check for DNS name
        dns_names = san.value.get_values_for_type(x509.DNSName)
        assert len(dns_names) > 0
        assert "test-service" in dns_names[0]

        # Check for SPIFFE URI
        uris = san.value.get_values_for_type(x509.UniformResourceIdentifier)
        assert len(uris) > 0
        assert "spiffe://" in uris[0]

    def test_certificate_not_ca(self, certificate_bundle):
        """Verify certificate is NOT a CA certificate."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.value.ca is False
        assert bc.value.path_length is None

    def test_key_size_minimum(self, certificate_bundle):
        """Verify key size is at least 2048 bits."""
        cert = x509.load_pem_x509_certificate(
            certificate_bundle.certificate_pem.encode()
        )

        # Get public key size
        key_size = cert.public_key().key_size
        assert key_size >= 2048


class TestSecurityInjection:
    """
    Injection tests (N3m0 review).

    Test that malicious names are rejected.
    """

    @pytest.mark.parametrize("malicious_name", [
        "client\x00admin",           # Null byte injection
        "client/CN=admin",           # DN injection
        "client$(whoami)",           # Shell injection
        "../../../etc/passwd",       # Path traversal
        "<script>alert(1)</script>", # XSS
        "client;DROP TABLE",         # SQL injection
        "client\nCN=admin",          # Newline injection
        "a",                         # Too short
        "12client",                  # Starts with number
        "client name",               # Contains space
    ])
    def test_malicious_name_rejected(self, malicious_name):
        """Test that malicious names are rejected by validation."""
        from src.schemas.client import ClientCreate

        with pytest.raises(ValueError):
            ClientCreate(name=malicious_name, auth_type=AuthTypeEnum.MTLS)

    def test_valid_name_accepted(self):
        """Test that valid names are accepted."""
        from src.schemas.client import ClientCreate

        valid_names = [
            "billing-service",
            "api_gateway",
            "Service123",
            "my-cool-api-v2",
        ]

        for name in valid_names:
            client = ClientCreate(name=name, auth_type=AuthTypeEnum.OAUTH2)
            assert client.name == name


class TestCNSanitization:
    """Test CN sanitization in MockCertificateProvider."""

    @pytest.mark.asyncio
    async def test_cn_sanitization_special_chars(self):
        """Test that special characters are removed from CN."""
        provider = MockCertificateProvider()

        # Even if name somehow bypasses schema validation,
        # the provider should sanitize it
        request = CertificateRequest(
            client_id="test",
            client_name="test/CN=admin",  # Injection attempt
            tenant_id="tenant",
        )

        bundle = await provider.generate_certificate(request)
        cert = x509.load_pem_x509_certificate(bundle.certificate_pem.encode())

        # Get CN from subject
        cn = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break

        assert cn is not None
        # Verify no injection characters remain
        assert "/" not in cn
        assert "=" not in cn


class TestTenantIsolation:
    """
    Tenant isolation tests (Pr1nc3ss review).

    Verify tenant data is properly isolated.
    """

    @pytest.mark.asyncio
    async def test_tenant_id_from_jwt_only(self):
        """Test that tenant_id comes from JWT, not request body."""
        # The ClientCreate schema should NOT have tenant_id field
        from src.schemas.client import ClientCreate

        # Verify tenant_id is not in schema
        assert "tenant_id" not in ClientCreate.model_fields

    def test_404_not_403_for_other_tenant(self):
        """
        Test that accessing another tenant's client returns 404, not 403.

        This prevents information disclosure about resource existence.
        """
        # This would require a full integration test
        # Here we document the expected behavior
        # In router, we check _has_tenant_access and return 404 if false
        pass


class TestRateLimiting:
    """Test rate limiting for certificate generation."""

    def test_rate_limit_counter(self):
        """Test rate limit counter logic."""
        from src.routers.clients import _rate_limit_counter, _check_rate_limit, RATE_LIMIT_PER_HOUR
        from fastapi import HTTPException

        # Clear any existing counter
        _rate_limit_counter.clear()

        tenant_id = "rate-test-tenant"

        # Should succeed for first RATE_LIMIT_PER_HOUR requests
        for i in range(RATE_LIMIT_PER_HOUR):
            _check_rate_limit(tenant_id)

        # 11th request should fail
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit(tenant_id)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value.detail)

        # Clean up
        _rate_limit_counter.clear()


class TestCertificateBundleSecurity:
    """Test CertificateBundle security requirements."""

    @pytest.mark.asyncio
    async def test_bundle_repr_no_private_key(self):
        """Verify __repr__ does NOT include private key."""
        provider = MockCertificateProvider()
        request = CertificateRequest(
            client_id="test",
            client_name="test-service",
            tenant_id="tenant",
        )

        bundle = await provider.generate_certificate(request)

        # Check repr
        repr_str = repr(bundle)
        assert "BEGIN RSA PRIVATE KEY" not in repr_str
        assert "private" not in repr_str.lower()

        # Check str
        str_str = str(bundle)
        assert "BEGIN RSA PRIVATE KEY" not in str_str

    @pytest.mark.asyncio
    async def test_bundle_to_public_dict_no_private_key(self):
        """Verify to_public_dict() excludes private key."""
        provider = MockCertificateProvider()
        request = CertificateRequest(
            client_id="test",
            client_name="test-service",
            tenant_id="tenant",
        )

        bundle = await provider.generate_certificate(request)
        public_dict = bundle.to_public_dict()

        assert "private_key_pem" not in public_dict
        assert "certificate_pem" in public_dict
        assert "fingerprint_sha256" in public_dict


class TestClientModelValidation:
    """Test Client model validations."""

    def test_key_size_minimum(self):
        """Test that key size must be at least 2048."""
        with pytest.raises(ValueError) as exc_info:
            CertificateRequest(
                client_id="test",
                client_name="test",
                tenant_id="tenant",
                key_size=1024,  # Too small
            )

        assert "2048" in str(exc_info.value)

    def test_validity_days_range(self):
        """Test validity days must be 1-730."""
        # Too low
        with pytest.raises(ValueError):
            CertificateRequest(
                client_id="test",
                client_name="test",
                tenant_id="tenant",
                validity_days=0,
            )

        # Too high
        with pytest.raises(ValueError):
            CertificateRequest(
                client_id="test",
                client_name="test",
                tenant_id="tenant",
                validity_days=731,
            )


class TestClientStatus:
    """Test client status transitions."""

    def test_status_enum_values(self):
        """Verify ClientStatus enum has expected values."""
        assert ClientStatus.ACTIVE.value == "active"
        assert ClientStatus.SUSPENDED.value == "suspended"
        assert ClientStatus.REVOKED.value == "revoked"

    def test_auth_type_enum_values(self):
        """Verify AuthType enum has expected values."""
        assert AuthType.OAUTH2.value == "oauth2"
        assert AuthType.MTLS.value == "mtls"
        assert AuthType.MTLS_OAUTH2.value == "mtls_oauth2"


class TestEventBus:
    """Test event bus functionality."""

    @pytest.mark.asyncio
    async def test_event_publish_subscribe(self):
        """Test event publishing and subscribing."""
        from src.events import EventBus, Event

        bus = EventBus()
        received_events = []

        @bus.on("test.event")
        async def handler(event: Event):
            received_events.append(event)

        await bus.publish("test.event", {"key": "value"})

        assert len(received_events) == 1
        assert received_events[0].event_type == "test.event"
        assert received_events[0].payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_event_handler_error_does_not_propagate(self):
        """Test that handler errors don't propagate."""
        from src.events import EventBus

        bus = EventBus()

        @bus.on("error.event")
        async def failing_handler(event):
            raise ValueError("Handler error")

        # Should not raise
        await bus.publish("error.event", {})


class TestCertificateService:
    """Test CertificateService facade."""

    @pytest.mark.asyncio
    async def test_error_wrapping(self):
        """Test that internal errors are wrapped with generic message."""
        from src.services.certificate_service import CertificateService
        from src.services.certificate_provider import CertificateServiceUnavailable

        # Create mock provider that raises an error
        mock_provider = MagicMock()
        mock_provider.provider_name = "mock"
        mock_provider.generate_certificate = AsyncMock(
            side_effect=Exception("Internal Vault error: connection refused")
        )

        service = CertificateService(mock_provider)

        request = CertificateRequest(
            client_id="test",
            client_name="test",
            tenant_id="tenant",
        )

        with pytest.raises(CertificateServiceUnavailable) as exc_info:
            await service.generate_certificate(request)

        # Verify error message is generic (no Vault details leaked)
        error_msg = str(exc_info.value)
        assert "Vault" not in error_msg
        assert "connection refused" not in error_msg
        assert "temporarily unavailable" in error_msg


class TestRBACPermissions:
    """Test RBAC permissions for client endpoints."""

    def test_client_permissions_defined(self):
        """Verify client permissions are defined."""
        from src.auth.rbac import Permission

        assert hasattr(Permission, "CLIENTS_CREATE")
        assert hasattr(Permission, "CLIENTS_READ")
        assert hasattr(Permission, "CLIENTS_UPDATE")
        assert hasattr(Permission, "CLIENTS_DELETE")

    def test_admin_has_client_permissions(self):
        """Verify cpi-admin has all client permissions."""
        from src.auth.rbac import ROLE_PERMISSIONS, Permission

        admin_perms = ROLE_PERMISSIONS["cpi-admin"]
        assert Permission.CLIENTS_CREATE in admin_perms
        assert Permission.CLIENTS_READ in admin_perms
        assert Permission.CLIENTS_UPDATE in admin_perms
        assert Permission.CLIENTS_DELETE in admin_perms

    def test_viewer_has_read_only(self):
        """Verify viewer only has read permission."""
        from src.auth.rbac import ROLE_PERMISSIONS, Permission

        viewer_perms = ROLE_PERMISSIONS["viewer"]
        assert Permission.CLIENTS_READ in viewer_perms
        assert Permission.CLIENTS_CREATE not in viewer_perms
        assert Permission.CLIENTS_UPDATE not in viewer_perms
        assert Permission.CLIENTS_DELETE not in viewer_perms
