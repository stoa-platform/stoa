"""Tests for gateway internal routes — auto-registration, heartbeat, config fetch.

Covers the full lifecycle: register → heartbeat → config → auth rejection.
"""
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


VALID_KEY = "test_key_123"
REGISTER_URL = "/v1/internal/gateways/register"
GW_KEY_HEADER = "X-Gateway-Key"


def _registration_payload(**overrides):
    """Build a valid registration payload."""
    defaults = {
        "hostname": "test-gateway-abc",
        "mode": "edge-mcp",
        "version": "0.1.0",
        "environment": "dev",
        "capabilities": ["rest", "mcp", "sse", "oidc"],
        "admin_url": "http://localhost:8080",
    }
    defaults.update(overrides)
    return defaults


def _make_gateway_instance(**overrides):
    """Create a mock GatewayInstance with real enum values for Pydantic serialization."""
    from src.models.gateway_instance import GatewayType, GatewayInstanceStatus

    gw_id = overrides.pop("id", uuid4())
    defaults = {
        "id": gw_id,
        "name": "test-gateway-abc-edgemcp-dev",
        "display_name": "STOA Gateway (edge-mcp)",
        "gateway_type": GatewayType.STOA_EDGE_MCP,
        "environment": "dev",
        "tenant_id": None,
        "base_url": "http://localhost:8080",
        "auth_config": {"type": "gateway_key"},
        "status": GatewayInstanceStatus.ONLINE,
        "last_health_check": datetime.now(UTC),
        "health_details": {"mode": "edge-mcp", "hostname": "test-gateway-abc"},
        "capabilities": ["rest", "mcp", "sse", "oidc"],
        "version": "0.1.0",
        "tags": ["mode:edge-mcp", "auto-registered"],
        "mode": "edge-mcp",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestGatewayRegistration:
    """POST /v1/internal/gateways/register"""

    def test_register_success(self, client):
        """New gateway registers successfully and returns 201."""
        gw = _make_gateway_instance()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "test-gateway-abc-edgemcp-dev"
            assert data["status"] == "online"
            mock_repo.create.assert_awaited_once()

    def test_register_idempotent(self, client):
        """Re-registering same gateway updates rather than duplicates (upsert)."""
        existing = _make_gateway_instance()
        updated = _make_gateway_instance(version="0.2.0")

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=existing)
            mock_repo.update = AsyncMock(return_value=updated)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(version="0.2.0"),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            mock_repo.update.assert_awaited_once()
            mock_repo.create.assert_not_called()

    def test_register_invalid_key_returns_401(self, client):
        """Invalid gateway key is rejected with 401."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(),
                headers={GW_KEY_HEADER: "wrong_key"},
            )

            assert resp.status_code == 401
            assert "Invalid gateway key" in resp.json()["detail"]

    def test_register_no_keys_configured_returns_503(self, client):
        """Registration disabled when GATEWAY_API_KEYS is empty."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = []

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(),
                headers={GW_KEY_HEADER: "any_key"},
            )

            assert resp.status_code == 503
            assert "disabled" in resp.json()["detail"].lower()

    def test_register_missing_key_header_returns_422(self, client):
        """Missing X-Gateway-Key header returns 422 validation error."""
        resp = client.post(REGISTER_URL, json=_registration_payload())
        assert resp.status_code == 422

    def test_register_mode_normalization(self, client):
        """Various mode strings are normalized correctly."""
        gw = _make_gateway_instance()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            # Test with underscore mode (should be normalized)
            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(mode="edge_mcp"),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201

    def test_register_sidecar_mode(self, client):
        """Sidecar mode registers with STOA_SIDECAR type."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            gateway_type=GatewayType.STOA_SIDECAR,
            mode="sidecar",
        )

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(mode="sidecar"),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201


class TestGatewayHeartbeat:
    """POST /v1/internal/gateways/{id}/heartbeat"""

    def test_heartbeat_success(self, client):
        """Heartbeat updates health metrics and returns 204."""
        gw = _make_gateway_instance()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            resp = client.post(
                f"/v1/internal/gateways/{gw.id}/heartbeat",
                json={
                    "uptime_seconds": 120,
                    "routes_count": 5,
                    "policies_count": 2,
                    "requests_total": 1000,
                    "error_rate": 0.01,
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 204
            # Verify health_details were updated with metrics
            assert gw.health_details["uptime_seconds"] == 120
            assert gw.health_details["requests_total"] == 1000
            assert gw.health_details["error_rate"] == 0.01

    def test_heartbeat_not_found_returns_404(self, client):
        """Heartbeat for non-existent gateway returns 404."""
        fake_id = uuid4()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/heartbeat",
                json={"uptime_seconds": 60},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 404

    def test_heartbeat_invalid_key_returns_401(self, client):
        """Heartbeat with invalid key is rejected."""
        fake_id = uuid4()

        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/heartbeat",
                json={"uptime_seconds": 60},
                headers={GW_KEY_HEADER: "wrong_key"},
            )

            assert resp.status_code == 401

    def test_heartbeat_preserves_registered_at(self, client):
        """Heartbeat merges metrics without overwriting registered_at."""
        registered_at = "2026-02-06T10:00:00+00:00"
        gw = _make_gateway_instance(
            health_details={
                "registered_at": registered_at,
                "mode": "edge-mcp",
                "hostname": "test-gateway-abc",
            },
        )

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            resp = client.post(
                f"/v1/internal/gateways/{gw.id}/heartbeat",
                json={"uptime_seconds": 300, "routes_count": 10},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 204
            assert gw.health_details["registered_at"] == registered_at
            assert gw.health_details["uptime_seconds"] == 300


class TestGatewayConfig:
    """GET /v1/internal/gateways/{id}/config"""

    def test_config_returns_gateway_info(self, client):
        """Config endpoint returns gateway info with empty deployments/policies."""
        gw = _make_gateway_instance()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo, \
             patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)

            MockDeployRepo.return_value.list_by_gateway = AsyncMock(return_value=[])
            MockPolicyRepo.return_value.list_all = AsyncMock(return_value=[])

            resp = client.get(
                f"/v1/internal/gateways/{gw.id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["gateway_id"] == str(gw.id)
            assert data["name"] == gw.name
            assert data["pending_deployments"] == []
            assert data["pending_policies"] == []

    def test_config_returns_pending_deployments(self, client):
        """Config includes pending deployments targeted at this gateway."""
        gw = _make_gateway_instance()
        deploy = MagicMock()
        deploy.id = uuid4()
        deploy.api_catalog_id = uuid4()
        deploy.sync_status = MagicMock(value="pending")
        deploy.desired_state = {"routes": ["/api/v1"]}
        deploy.sync_attempts = 0

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo, \
             patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)

            MockDeployRepo.return_value.list_by_gateway = AsyncMock(return_value=[deploy])
            MockPolicyRepo.return_value.list_all = AsyncMock(return_value=[])

            resp = client.get(
                f"/v1/internal/gateways/{gw.id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["pending_deployments"]) == 1
            assert data["pending_deployments"][0]["sync_status"] == "pending"

    def test_config_returns_policies(self, client):
        """Config includes applicable policies for the gateway."""
        gw = _make_gateway_instance()
        policy = MagicMock()
        policy.id = uuid4()
        policy.name = "rate-limit-default"
        policy.policy_type = MagicMock(value="rate_limit")
        policy.config = {"requests_per_minute": 100}
        policy.priority = 10
        policy.enabled = True

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo, \
             patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)

            MockDeployRepo.return_value.list_by_gateway = AsyncMock(return_value=[])
            MockPolicyRepo.return_value.list_all = AsyncMock(return_value=[policy])

            resp = client.get(
                f"/v1/internal/gateways/{gw.id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["pending_policies"]) == 1
            assert data["pending_policies"][0]["name"] == "rate-limit-default"
            assert data["pending_policies"][0]["policy_type"] == "rate_limit"

    def test_config_not_found_returns_404(self, client):
        """Config for non-existent gateway returns 404."""
        fake_id = uuid4()

        with patch("src.routers.gateway_internal.settings") as mock_settings, \
             patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo:

            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            resp = client.get(
                f"/v1/internal/gateways/{fake_id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 404


class TestHelperFunctions:
    """Unit tests for internal helper functions."""

    def test_derive_instance_name(self):
        """Instance name is deterministic: hostname-mode-environment."""
        from src.routers.gateway_internal import _derive_instance_name

        assert _derive_instance_name("gw-abc", "edge_mcp", "prod") == "gw-abc-edgemcp-prod"
        assert _derive_instance_name("gw-xyz", "sidecar", "dev") == "gw-xyz-sidecar-dev"

    def test_mode_to_gateway_type(self):
        """Mode strings map to correct GatewayType enum values."""
        from src.routers.gateway_internal import _mode_to_gateway_type
        from src.models.gateway_instance import GatewayType

        assert _mode_to_gateway_type("edge-mcp") == GatewayType.STOA_EDGE_MCP
        assert _mode_to_gateway_type("edge_mcp") == GatewayType.STOA_EDGE_MCP
        assert _mode_to_gateway_type("sidecar") == GatewayType.STOA_SIDECAR
        assert _mode_to_gateway_type("unknown") == GatewayType.STOA

    def test_normalize_mode(self):
        """Mode normalization handles all variants."""
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("edge-mcp") == "edge-mcp"
        assert _normalize_mode("edge_mcp") == "edge-mcp"
        assert _normalize_mode("edgemcp") == "edge-mcp"
        assert _normalize_mode("mcp") == "edge-mcp"
        assert _normalize_mode("sidecar") == "sidecar"
        assert _normalize_mode("proxy") == "proxy"
        assert _normalize_mode("shadow") == "shadow"
        assert _normalize_mode("unknown") == "edge-mcp"  # default fallback
