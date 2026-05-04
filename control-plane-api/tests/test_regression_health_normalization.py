"""Regression tests for CAB-1916: health check normalization.

The bug: heartbeat stores `discovered_apis` as int, discovery stores it as array.
JSONB merge means whoever writes last determines the type — race condition.

Fix: heartbeat stores `discovered_apis_count` (int), discovery stores
`discovered_apis` (array) + `discovered_apis_count` (int). No key collision.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

VALID_KEY = "test_key_abc"
GW_KEY_HEADER = "X-Gateway-Key"


def _make_gateway_instance(**overrides):
    from src.models.gateway_instance import GatewayInstanceStatus, GatewayType

    gw_id = overrides.pop("id", uuid4())
    defaults = {
        "id": gw_id,
        "name": "gw-connect-prod",
        "display_name": "STOA Connect (connect)",
        "gateway_type": GatewayType.STOA,
        "environment": "prod",
        "tenant_id": None,
        "base_url": "http://localhost:8080",
        "auth_config": {"type": "gateway_key"},
        "status": GatewayInstanceStatus.ONLINE,
        "last_health_check": datetime.now(UTC),
        "health_details": {},
        "capabilities": ["policy_sync", "health_monitoring"],
        "version": "0.1.0",
        "tags": ["mode:connect", "auto-registered"],
        "mode": "connect",
        "protected": False,
        "deleted_at": None,
        "deleted_by": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestRegressionCAB1916HeartbeatDiscoveryRace:
    """CAB-1916: heartbeat must not overwrite discovery's `discovered_apis` array."""

    def test_heartbeat_stores_discovered_apis_count_not_discovered_apis(self, client):
        """Non-edge heartbeat must store `discovered_apis_count` (int), never `discovered_apis`.

        Before the fix, heartbeat stored `discovered_apis: 5` (int) which
        would overwrite the discovery array `discovered_apis: [{...}]`.
        """
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
                json={"uptime_seconds": 60, "discovered_apis": 5},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        # The fix: heartbeat must store as `discovered_apis_count`, not `discovered_apis`
        assert "discovered_apis_count" in gw.health_details
        assert gw.health_details["discovered_apis_count"] == 5
        # `discovered_apis` key must NOT be set by heartbeat (it's reserved for discovery array)
        assert "discovered_apis" not in gw.health_details or isinstance(
            gw.health_details.get("discovered_apis"), list
        )

    def test_edge_mcp_heartbeat_stores_tools_count_not_api_discovery_count(self, client):
        """Edge MCP heartbeat reports MCP tools, not discovered/deployed APIs."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            gateway_type=GatewayType.STOA_EDGE_MCP,
            mode="edge-mcp",
            health_details={"discovered_apis_count": 51},
        )

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
                json={"uptime_seconds": 60, "discovered_apis": 51},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert gw.health_details["mcp_tools_count"] == 51
        assert gw.health_details["discovered_apis_count"] == 0
        assert "discovered_apis" not in gw.health_details

    def test_sidecar_heartbeat_stores_tools_count_not_api_discovery_count(self, client):
        """Sidecar heartbeat also reports runtime tools in the legacy field."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            gateway_type=GatewayType.STOA_SIDECAR,
            mode="sidecar",
            health_details={"discovered_apis_count": 15},
        )

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
                json={"uptime_seconds": 60, "routes_count": 2, "discovered_apis": 15},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert gw.health_details["mcp_tools_count"] == 15
        assert gw.health_details["discovered_apis_count"] == 0
        assert "discovered_apis" not in gw.health_details

    def test_sidecar_heartbeat_preserves_discovery_array_count(self, client):
        """Runtime tool heartbeat must not replace a real discovery report."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            gateway_type=GatewayType.STOA_SIDECAR,
            mode="sidecar",
            health_details={
                "discovered_apis_count": 2,
                "discovered_apis": [
                    {"name": "manual-test-1777312098", "is_active": True},
                    {"name": "fapi-banking", "is_active": True},
                ],
            },
        )

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
                json={"uptime_seconds": 60, "routes_count": 2, "discovered_apis": 15},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert gw.health_details["mcp_tools_count"] == 15
        assert gw.health_details["discovered_apis_count"] == 2
        assert len(gw.health_details["discovered_apis"]) == 2

    def test_heartbeat_after_discovery_preserves_api_array(self, client):
        """Heartbeat after discovery must not overwrite the `discovered_apis` array.

        Sequence: discovery sets discovered_apis=[{...}], then heartbeat runs.
        Before the fix, heartbeat would replace the array with an integer.
        """
        discovery_data = [
            {"name": "petstore", "version": "1.0", "is_active": True},
            {"name": "payments", "version": "2.0", "is_active": True},
        ]
        # Start with discovery data already stored
        gw = _make_gateway_instance(
            health_details={
                "last_discovery": "2026-03-26T08:00:00",
                "discovered_apis_count": 2,
                "discovered_apis": discovery_data,
            }
        )

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
                json={"uptime_seconds": 120, "discovered_apis": 3},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        # After heartbeat, `discovered_apis` must still be the array from discovery
        assert isinstance(gw.health_details["discovered_apis"], list)
        assert len(gw.health_details["discovered_apis"]) == 2
        assert gw.health_details["discovered_apis"][0]["name"] == "petstore"
        # Count updated by heartbeat
        assert gw.health_details["discovered_apis_count"] == 3

    def test_discovery_after_heartbeat_preserves_count(self, client):
        """Discovery after heartbeat must update both array and count."""
        # Start with heartbeat data
        gw = _make_gateway_instance(
            health_details={
                "last_heartbeat": "2026-03-26T08:00:00",
                "uptime_seconds": 60,
                "discovered_apis_count": 0,
                "routes_count": 0,
            }
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            client.post(
                f"/v1/internal/gateways/{gw.id}/discovery",
                json={
                    "apis": [
                        {"name": "petstore", "version": "1.0", "is_active": True},
                    ]
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        # Discovery sets the array
        assert isinstance(gw.health_details["discovered_apis"], list)
        assert len(gw.health_details["discovered_apis"]) == 1
        # Discovery also sets the count
        assert gw.health_details["discovered_apis_count"] == 1
        # Heartbeat fields preserved
        assert gw.health_details["uptime_seconds"] == 60

    def test_routes_count_stored_from_heartbeat(self, client):
        """routes_count from heartbeat is stored in health_details."""
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
                json={
                    "uptime_seconds": 300,
                    "routes_count": 12,
                    "policies_count": 3,
                    "discovered_apis": 5,
                    "requests_total": 1000,
                    "error_rate": 0.01,
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert gw.health_details["routes_count"] == 12
        assert gw.health_details["policies_count"] == 3
        assert gw.health_details["discovered_apis_count"] == 5
        assert gw.health_details["requests_total"] == 1000
        assert gw.health_details["error_rate"] == 0.01
