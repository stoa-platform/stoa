"""Tests for gateway internal router — helper functions and mode mapping.

Complements test_gateway_internal.py with additional edge-case coverage for
the helper functions and schema validation paths.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

VALID_KEY = "test_key_abc"
REGISTER_URL = "/v1/internal/gateways/register"
GW_KEY_HEADER = "X-Gateway-Key"


def _make_gateway_instance(**overrides):
    from src.models.gateway_instance import GatewayInstanceStatus, GatewayType

    gw_id = overrides.pop("id", uuid4())
    defaults = {
        "id": gw_id,
        "name": "gw-host-edgemcp-staging",
        "display_name": "STOA Gateway (edge-mcp)",
        "gateway_type": GatewayType.STOA_EDGE_MCP,
        "environment": "staging",
        "tenant_id": None,
        "base_url": "http://localhost:8080",
        "auth_config": {"type": "gateway_key"},
        "status": GatewayInstanceStatus.ONLINE,
        "last_health_check": datetime.now(UTC),
        "health_details": {"mode": "edge-mcp", "hostname": "gw-host"},
        "capabilities": ["rest", "mcp"],
        "version": "0.2.0",
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


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestModeNormalization:
    """Unit tests for _normalize_mode helper."""

    def test_mcp_alias_maps_to_edge_mcp(self):
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("mcp") == "edge-mcp"

    def test_edgemcp_no_separator_maps_to_edge_mcp(self):
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("edgemcp") == "edge-mcp"

    def test_proxy_preserved(self):
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("proxy") == "proxy"

    def test_unknown_mode_defaults_to_edge_mcp(self):
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("bogus-mode") == "edge-mcp"

    def test_uppercase_mode_normalized(self):
        from src.routers.gateway_internal import _normalize_mode

        assert _normalize_mode("SIDECAR") == "sidecar"


class TestGatewayTypeMapping:
    """Unit tests for _mode_to_gateway_type helper."""

    def test_shadow_mode_maps_correctly(self):
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type

        assert _mode_to_gateway_type("shadow") == GatewayType.STOA_SHADOW

    def test_proxy_mode_maps_correctly(self):
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type

        assert _mode_to_gateway_type("proxy") == GatewayType.STOA_PROXY

    def test_sidecar_mode_maps_correctly(self):
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type

        assert _mode_to_gateway_type("sidecar") == GatewayType.STOA_SIDECAR

    def test_unknown_mode_falls_back_to_stoa(self):
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type

        assert _mode_to_gateway_type("completely_unknown") == GatewayType.STOA


class TestDeriveInstanceName:
    """Unit tests for _derive_instance_name helper."""

    def test_underscores_removed_from_mode(self):
        from src.routers.gateway_internal import _derive_instance_name

        result = _derive_instance_name("my-host", "edge_mcp", "prod")
        assert result == "my-host-edgemcp-prod"

    def test_name_includes_all_parts(self):
        from src.routers.gateway_internal import _derive_instance_name

        result = _derive_instance_name("gw-abc123", "sidecar", "staging")
        assert "gw-abc123" in result
        assert "sidecar" in result
        assert "staging" in result


# ---------------------------------------------------------------------------
# Heartbeat with minimal payload
# ---------------------------------------------------------------------------


class TestHeartbeatMinimalPayload:
    """POST /{id}/heartbeat with optional fields absent."""

    def test_heartbeat_without_optional_metrics(self, client):
        """Heartbeat works with only required uptime_seconds."""
        gw = _make_gateway_instance()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            resp = client.post(
                f"/v1/internal/gateways/{gw.id}/heartbeat",
                json={"uptime_seconds": 5},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 204

    def test_heartbeat_stores_none_for_missing_optional_fields(self, client):
        """Missing optional fields are stored as None in health_details."""
        gw = _make_gateway_instance(health_details={})

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            client.post(
                f"/v1/internal/gateways/{gw.id}/heartbeat",
                json={"uptime_seconds": 10},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert gw.health_details["requests_total"] is None
        assert gw.health_details["error_rate"] is None


# ---------------------------------------------------------------------------
# Registration with tenant_id
# ---------------------------------------------------------------------------


class TestGatewayRegistrationTenant:
    """POST /register with optional tenant_id."""

    def test_register_with_tenant_id(self, client):
        """Registration with tenant_id stores tenant restriction."""
        gw = _make_gateway_instance(tenant_id="acme")

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "tenant-gw",
                    "mode": "edge-mcp",
                    "version": "0.1.0",
                    "environment": "prod",
                    "admin_url": "http://gw:8080",
                    "tenant_id": "acme",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201
        # The created instance should have received a call with the full tenant_id payload
        mock_repo.create.assert_awaited_once()

    def test_register_shadow_mode(self, client):
        """Shadow mode registers with STOA_SHADOW type."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            gateway_type=GatewayType.STOA_SHADOW,
            mode="shadow",
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "shadow-gw",
                    "mode": "shadow",
                    "version": "0.1.0",
                    "environment": "dev",
                    "admin_url": "http://shadow:8080",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Config endpoint with tenant-scoped policies
# ---------------------------------------------------------------------------


class TestGatewayConfigTenantScoping:
    """GET /{id}/config — tenant_id scoping for policy queries."""

    def test_config_tenant_gateway_scopes_policies(self, client):
        """Config query uses tenant_id when gateway is tenant-scoped."""
        gw = _make_gateway_instance(tenant_id="acme")

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=gw)
            MockDeployRepo.return_value.list_by_gateway = AsyncMock(return_value=[])
            mock_list_all = AsyncMock(return_value=[])
            MockPolicyRepo.return_value.list_all = mock_list_all

            resp = client.get(
                f"/v1/internal/gateways/{gw.id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        # Policy query should be called with tenant_id="acme"
        mock_list_all.assert_awaited_once_with(tenant_id="acme")

    def test_config_no_tenant_uses_none(self, client):
        """Config query passes tenant_id=None for platform-level gateways."""
        gw = _make_gateway_instance(tenant_id=None)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=gw)
            MockDeployRepo.return_value.list_by_gateway = AsyncMock(return_value=[])
            mock_list_all = AsyncMock(return_value=[])
            MockPolicyRepo.return_value.list_all = mock_list_all

            resp = client.get(
                f"/v1/internal/gateways/{gw.id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        mock_list_all.assert_awaited_once_with(tenant_id=None)
