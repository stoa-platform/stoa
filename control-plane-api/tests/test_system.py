"""Tests for system info endpoint (CAB-1311)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.schemas.system import (
    Edition,
    LicenseInfo,
    SystemInfoResponse,
    get_features_for_edition,
)

# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------


class TestEdition:
    def test_community_is_default(self):
        assert Edition.COMMUNITY.value == "community"

    def test_all_editions(self):
        assert {e.value for e in Edition} == {"community", "standard", "enterprise"}

    def test_edition_from_string(self):
        assert Edition("community") == Edition.COMMUNITY
        assert Edition("standard") == Edition.STANDARD
        assert Edition("enterprise") == Edition.ENTERPRISE


class TestFeatureFlags:
    def test_community_defaults(self):
        flags = get_features_for_edition(Edition.COMMUNITY)
        # Core features ON
        assert flags.api_catalog is True
        assert flags.mcp_gateway is True
        assert flags.developer_portal is True
        assert flags.rbac is True
        assert flags.rate_limiting is True
        assert flags.openapi_to_mcp is True
        # Standard+ features OFF
        assert flags.sso_oidc is False
        assert flags.audit_trail is False
        assert flags.tenant_export_import is False
        # Enterprise features OFF
        assert flags.mcp_federation is False
        assert flags.wasm_plugins is False

    def test_standard_features(self):
        flags = get_features_for_edition(Edition.STANDARD)
        # Core ON
        assert flags.api_catalog is True
        # Standard ON
        assert flags.sso_oidc is True
        assert flags.audit_trail is True
        assert flags.tenant_export_import is True
        assert flags.webhook_delivery is True
        assert flags.custom_policies is True
        # Enterprise OFF
        assert flags.mcp_federation is False
        assert flags.wasm_plugins is False

    def test_enterprise_all_features(self):
        flags = get_features_for_edition(Edition.ENTERPRISE)
        # All features ON
        for field_name, value in flags.model_dump().items():
            assert value is True, f"Enterprise should have {field_name}=True"

    def test_feature_flags_serialization(self):
        flags = get_features_for_edition(Edition.COMMUNITY)
        data = flags.model_dump()
        assert isinstance(data, dict)
        assert "api_catalog" in data
        assert "mcp_federation" in data


class TestLicenseInfo:
    def test_community_license(self):
        info = LicenseInfo(
            edition=Edition.COMMUNITY,
            license_type="Apache-2.0",
        )
        assert info.license_type == "Apache-2.0"
        assert "github.com" in info.license_url

    def test_commercial_license(self):
        info = LicenseInfo(
            edition=Edition.ENTERPRISE,
            license_type="Commercial",
            license_url="https://gostoa.dev/pricing",
        )
        assert info.license_type == "Commercial"


class TestSystemInfoResponse:
    def test_response_structure(self):
        resp = SystemInfoResponse(
            version="2.0.0",
            environment="production",
            license=LicenseInfo(
                edition=Edition.COMMUNITY,
                license_type="Apache-2.0",
            ),
            features=get_features_for_edition(Edition.COMMUNITY),
        )
        assert resp.platform == "STOA Platform"
        assert resp.tagline == "The European Agent Gateway"
        assert resp.version == "2.0.0"
        assert resp.license.edition == Edition.COMMUNITY

    def test_serialization_roundtrip(self):
        resp = SystemInfoResponse(
            version="2.0.0",
            environment="dev",
            license=LicenseInfo(
                edition=Edition.STANDARD,
                license_type="Commercial",
                license_url="https://gostoa.dev/pricing",
            ),
            features=get_features_for_edition(Edition.STANDARD),
        )
        data = resp.model_dump()
        restored = SystemInfoResponse(**data)
        assert restored.version == "2.0.0"
        assert restored.license.edition == Edition.STANDARD
        assert restored.features.sso_oidc is True


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestSystemInfoEndpoint:
    @pytest.fixture
    def client(self):
        """Create test client with mocked auth."""
        with patch("src.main.lifespan"):
            from src.main import app

            return TestClient(app, raise_server_exceptions=False)

    def test_system_info_returns_200(self, client):
        """System info endpoint should be publicly accessible."""
        response = client.get("/v1/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "STOA Platform"
        assert "version" in data
        assert "license" in data
        assert "features" in data

    def test_system_info_includes_edition(self, client):
        """Response should include edition info."""
        response = client.get("/v1/system/info")
        data = response.json()
        assert data["license"]["edition"] in ["community", "standard", "enterprise"]

    def test_system_info_includes_features(self, client):
        """Response should include feature flags."""
        response = client.get("/v1/system/info")
        data = response.json()
        features = data["features"]
        assert "api_catalog" in features
        assert "mcp_gateway" in features
        assert "mcp_federation" in features

    def test_system_info_default_community(self, client):
        """Default edition should be community with Apache-2.0 license."""
        response = client.get("/v1/system/info")
        data = response.json()
        assert data["license"]["license_type"] == "Apache-2.0"

    def test_system_info_includes_docs_url(self, client):
        """Response should include documentation URL."""
        response = client.get("/v1/system/info")
        data = response.json()
        assert data["docs_url"] == "https://docs.gostoa.dev"
        assert data["repository"] == "https://github.com/stoa-platform/stoa"
