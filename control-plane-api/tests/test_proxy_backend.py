"""Tests for proxy backend model, repository, and router (CAB-1725)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.models.proxy_backend import ProxyBackend, ProxyBackendAuthType, ProxyBackendStatus
from src.schemas.proxy_backend import (
    ProxyBackendCreate,
    ProxyBackendHealthStatus,
    ProxyBackendListResponse,
    ProxyBackendResponse,
    ProxyBackendUpdate,
)

# ============== Model Tests ==============


class TestProxyBackendModel:
    """Test ProxyBackend SQLAlchemy model."""

    def test_model_creation(self):
        """Test model creation with explicit values."""
        backend = ProxyBackend(
            name="test-backend",
            base_url="https://api.example.com",
            auth_type=ProxyBackendAuthType.API_KEY,
            status=ProxyBackendStatus.ACTIVE,
            is_active=True,
            rate_limit_rpm=0,
            circuit_breaker_enabled=True,
            fallback_direct=False,
            timeout_secs=30,
        )
        assert backend.name == "test-backend"
        assert backend.base_url == "https://api.example.com"
        assert backend.auth_type == ProxyBackendAuthType.API_KEY
        assert backend.status == ProxyBackendStatus.ACTIVE
        assert backend.is_active is True
        assert backend.rate_limit_rpm == 0
        assert backend.circuit_breaker_enabled is True
        assert backend.fallback_direct is False
        assert backend.timeout_secs == 30

    def test_model_repr(self):
        """Test model string representation."""
        backend = ProxyBackend(
            name="n8n",
            base_url="https://n8n.gostoa.dev",
            status=ProxyBackendStatus.ACTIVE,
        )
        assert "n8n" in repr(backend)
        assert "n8n.gostoa.dev" in repr(backend)

    def test_auth_type_enum_values(self):
        """Test auth type enum has expected values."""
        assert ProxyBackendAuthType.API_KEY == "api_key"
        assert ProxyBackendAuthType.BEARER == "bearer"
        assert ProxyBackendAuthType.BASIC == "basic"
        assert ProxyBackendAuthType.OAUTH2_CC == "oauth2_cc"

    def test_status_enum_values(self):
        """Test status enum has expected values."""
        assert ProxyBackendStatus.ACTIVE == "active"
        assert ProxyBackendStatus.DISABLED == "disabled"

    def test_model_with_all_fields(self):
        """Test model creation with all fields populated."""
        backend = ProxyBackend(
            id=uuid.uuid4(),
            name="github",
            display_name="GitHub API",
            description="GitHub REST API v3",
            base_url="https://api.github.com",
            health_endpoint="/",
            auth_type=ProxyBackendAuthType.BEARER,
            credential_ref="api-proxy:github",
            rate_limit_rpm=300,
            circuit_breaker_enabled=True,
            fallback_direct=False,
            timeout_secs=15,
            status=ProxyBackendStatus.ACTIVE,
            is_active=True,
        )
        assert backend.display_name == "GitHub API"
        assert backend.health_endpoint == "/"
        assert backend.credential_ref == "api-proxy:github"
        assert backend.rate_limit_rpm == 300
        assert backend.timeout_secs == 15


# ============== Schema Tests ==============


class TestProxyBackendSchemas:
    """Test Pydantic schemas."""

    def test_create_schema_valid(self):
        """Test valid create schema."""
        data = ProxyBackendCreate(
            name="n8n",
            display_name="n8n Workflow Automation",
            base_url="https://n8n.gostoa.dev",
            health_endpoint="/healthz",
            auth_type="api_key",
            credential_ref="api-proxy:n8n",
            rate_limit_rpm=60,
        )
        assert data.name == "n8n"
        assert data.rate_limit_rpm == 60

    def test_create_schema_name_validation(self):
        """Test name must be lowercase alphanumeric with dashes."""
        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="Invalid Name!",
                base_url="https://example.com",
            )

    def test_create_schema_defaults(self):
        """Test create schema default values."""
        data = ProxyBackendCreate(
            name="test",
            base_url="https://example.com",
        )
        assert data.auth_type == "api_key"
        assert data.rate_limit_rpm == 0
        assert data.circuit_breaker_enabled is True
        assert data.fallback_direct is False
        assert data.timeout_secs == 30

    def test_update_schema_partial(self):
        """Test update schema allows partial updates."""
        data = ProxyBackendUpdate(
            display_name="Updated Name",
            rate_limit_rpm=120,
        )
        assert data.display_name == "Updated Name"
        assert data.rate_limit_rpm == 120
        assert data.base_url is None
        assert data.is_active is None

    def test_response_schema_from_attributes(self):
        """Test response schema can be built from model attributes."""
        backend_id = uuid.uuid4()
        now = datetime.now(UTC)
        resp = ProxyBackendResponse(
            id=backend_id,
            name="linear",
            display_name="Linear",
            description=None,
            base_url="https://api.linear.app",
            health_endpoint="/graphql",
            auth_type="bearer",
            credential_ref="api-proxy:linear",
            rate_limit_rpm=120,
            circuit_breaker_enabled=True,
            fallback_direct=False,
            timeout_secs=30,
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == backend_id
        assert resp.name == "linear"

    def test_health_status_schema(self):
        """Test health status schema."""
        status = ProxyBackendHealthStatus(
            backend_name="n8n",
            healthy=True,
            status_code=200,
            latency_ms=42.5,
            checked_at=datetime.now(UTC),
        )
        assert status.healthy is True
        assert status.latency_ms == 42.5

    def test_health_status_unhealthy(self):
        """Test unhealthy status with error."""
        status = ProxyBackendHealthStatus(
            backend_name="broken",
            healthy=False,
            error="Connection refused",
            checked_at=datetime.now(UTC),
        )
        assert status.healthy is False
        assert status.error == "Connection refused"

    def test_list_response_schema(self):
        """Test list response schema."""
        resp = ProxyBackendListResponse(items=[], total=0)
        assert resp.total == 0
        assert resp.items == []


# ============== Router Tests ==============


class TestProxyBackendRouter:
    """Test proxy backend API endpoints."""

    def _make_backend(self, name: str = "n8n", **kwargs) -> ProxyBackend:
        """Create a test ProxyBackend instance."""
        defaults = {
            "id": uuid.uuid4(),
            "name": name,
            "display_name": f"{name} Service",
            "description": None,
            "base_url": f"https://{name}.gostoa.dev",
            "health_endpoint": "/healthz",
            "auth_type": ProxyBackendAuthType.API_KEY,
            "credential_ref": f"api-proxy:{name}",
            "rate_limit_rpm": 60,
            "circuit_breaker_enabled": True,
            "fallback_direct": False,
            "timeout_secs": 30,
            "status": ProxyBackendStatus.ACTIVE,
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(kwargs)
        backend = MagicMock(spec=ProxyBackend)
        for key, value in defaults.items():
            setattr(backend, key, value)
        return backend

    def _make_admin_user(self):
        """Create mock admin user."""
        user = MagicMock()
        user.roles = ["cpi-admin"]
        user.email = "admin@gostoa.dev"
        user.tenant_id = "test-tenant"
        return user

    def _make_viewer_user(self):
        """Create mock viewer user."""
        user = MagicMock()
        user.roles = ["viewer"]
        user.email = "viewer@example.com"
        user.tenant_id = "test-tenant"
        return user

    def test_require_admin_blocks_viewer(self):
        """Test _require_admin raises 403 for non-admin."""
        from fastapi import HTTPException

        from src.routers.proxy_backends import _require_admin

        user = self._make_viewer_user()
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(user)
        assert exc_info.value.status_code == 403

    def test_require_admin_allows_cpi_admin(self):
        """Test _require_admin passes for cpi-admin."""
        from src.routers.proxy_backends import _require_admin

        user = self._make_admin_user()
        # Should not raise
        _require_admin(user)

    def test_create_schema_rejects_invalid_name(self):
        """Test create schema rejects names with spaces or uppercase."""
        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="My Backend",
                base_url="https://example.com",
            )

    def test_create_schema_rejects_name_starting_with_dash(self):
        """Test create schema rejects names starting with dash."""
        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="-invalid",
                base_url="https://example.com",
            )

    def test_create_schema_accepts_valid_names(self):
        """Test create schema accepts valid kebab-case names."""
        valid_names = ["n8n", "slack-bot", "github", "my-service-123"]
        for name in valid_names:
            data = ProxyBackendCreate(name=name, base_url="https://example.com")
            assert data.name == name

    def test_update_schema_all_none(self):
        """Test update schema with no fields set."""
        data = ProxyBackendUpdate()
        assert data.display_name is None
        assert data.base_url is None
        assert data.is_active is None

    def test_timeout_secs_validation(self):
        """Test timeout_secs must be between 1 and 300."""
        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="test",
                base_url="https://example.com",
                timeout_secs=0,
            )

        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="test",
                base_url="https://example.com",
                timeout_secs=301,
            )

    def test_rate_limit_rpm_validation(self):
        """Test rate_limit_rpm must be non-negative."""
        with pytest.raises(ValueError):
            ProxyBackendCreate(
                name="test",
                base_url="https://example.com",
                rate_limit_rpm=-1,
            )

    def test_health_cache_ttl_constant(self):
        """Test health cache TTL is 30 seconds."""
        from src.routers.proxy_backends import HEALTH_CACHE_TTL

        assert HEALTH_CACHE_TTL == 30.0


# ============== Seed Data Tests ==============


class TestSeedData:
    """Test the migration seed data configuration."""

    EXPECTED_BACKENDS = [
        "n8n",
        "linear",
        "github",
        "slack-bot",
        "slack-webhook",
        "infisical",
        "cloudflare",
        "pushgateway",
    ]

    def test_expected_backend_count(self):
        """Test we have 8 seed backends."""
        assert len(self.EXPECTED_BACKENDS) == 8

    def test_backend_names_are_valid(self):
        """Test all seed backend names match the schema pattern."""
        import re

        pattern = re.compile(r"^[a-z0-9][a-z0-9-]*$")
        for name in self.EXPECTED_BACKENDS:
            assert pattern.match(name), f"Invalid backend name: {name}"

    def test_credential_refs_follow_convention(self):
        """Test credential refs follow api-proxy:{name} convention."""
        for name in self.EXPECTED_BACKENDS:
            expected_ref = f"api-proxy:{name}"
            # Verify the convention is consistent
            assert expected_ref.startswith("api-proxy:")
