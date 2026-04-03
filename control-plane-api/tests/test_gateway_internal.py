"""Tests for gateway internal routes — auto-registration, heartbeat, config fetch.

Covers the full lifecycle: register → heartbeat → config → auth rejection.
"""

from datetime import UTC, datetime
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
    from src.models.gateway_instance import GatewayInstanceStatus, GatewayType

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
        "target_gateway_url": None,
        "public_url": None,
        "ui_url": None,
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


class TestGatewayRegistration:
    """POST /v1/internal/gateways/register"""

    def test_register_success(self, client):
        """New gateway registers successfully and returns 201."""
        gw = _make_gateway_instance()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

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

    def test_register_cancel_and_replace_soft_deletes_stale(self, client):
        """When a gateway re-registers with a new hostname (e.g. container
        recreated), stale entries with the same mode+env are soft-deleted
        so the Console doesn't show duplicates (CAB-1908)."""
        stale = _make_gateway_instance(
            name="old-hostname-connect-production",
            mode="connect",
            source="self_register",
        )
        new_gw = _make_gateway_instance(
            name="connect-kong-connect-production",
            mode="connect",
            source="self_register",
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            # Step 1: no exact name match (hostname changed)
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            # Step 1b: find stale entries with same mode+env
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[stale])
            mock_repo.soft_delete = AsyncMock(return_value=stale)
            # Step 2: no ArgoCD entry
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
            # Step 3: create new entry
            mock_repo.create = AsyncMock(return_value=new_gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(
                    hostname="connect-kong",
                    mode="connect",
                    environment="production",
                ),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            # Stale entry was soft-deleted
            mock_repo.soft_delete.assert_awaited_once_with(
                stale, deleted_by="replaced-by:connect-kong-connect-production"
            )
            # New entry was created
            mock_repo.create.assert_awaited_once()

    def test_register_cancel_and_replace_no_stale(self, client):
        """No soft-deletes when there are no stale entries (clean registration)."""
        gw = _make_gateway_instance()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            mock_repo.soft_delete.assert_not_called()

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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(mode="sidecar"),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201

    def test_register_connect_mode(self, client):
        """Connect mode registers with STOA type and preserves mode as 'connect' (CAB-1819)."""
        from src.models.gateway_instance import GatewayType

        gw = _make_gateway_instance(
            name="kong-vps-connect-production",
            display_name="STOA Gateway (connect)",
            gateway_type=GatewayType.STOA,
            mode="connect",
            tags=["mode:connect", "auto-registered"],
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(
                    hostname="kong-vps",
                    mode="connect",
                    environment="production",
                    capabilities=["rest"],
                    admin_url="http://kong-vps:8001",
                ),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            data = resp.json()
            assert data["mode"] == "connect"
            assert data["gateway_type"] == "stoa"
            mock_repo.create.assert_awaited_once()

    def test_register_adopts_argocd_entry(self, client):
        """Gateway registration adopts existing ArgoCD entry instead of creating duplicate."""
        argocd_gw = _make_gateway_instance(
            name="argocd-stoa-gateway",
            source="argocd",
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)  # No exact name match
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=argocd_gw)
            mock_repo.update = AsyncMock(return_value=argocd_gw)

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            mock_repo.update.assert_awaited_once()
            mock_repo.create.assert_not_called()
            # Verify it returned the ArgoCD entry
            assert resp.json()["name"] == "argocd-stoa-gateway"

    def test_register_prefers_name_match_over_argocd(self, client):
        """Re-registration by name takes priority over ArgoCD adoption."""
        existing = _make_gateway_instance()
        updated = _make_gateway_instance(version="0.3.0")

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]

            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=existing)  # Name match found
            mock_repo.update = AsyncMock(return_value=updated)
            # get_by_source_and_type should NOT be called when name matches
            mock_repo.get_by_source_and_type = AsyncMock()

            resp = client.post(
                REGISTER_URL,
                json=_registration_payload(version="0.3.0"),
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 201
            mock_repo.get_by_source_and_type.assert_not_awaited()


class TestGatewayHeartbeat:
    """POST /v1/internal/gateways/{id}/heartbeat"""

    def test_heartbeat_success(self, client):
        """Heartbeat updates health metrics and returns 204."""
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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo,
        ):

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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo,
        ):

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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.GatewayPolicyRepository") as MockPolicyRepo,
        ):

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

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):

            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            resp = client.get(
                f"/v1/internal/gateways/{fake_id}/config",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 404


class TestGatewayDiscovery:
    """POST /v1/internal/gateways/{id}/discovery"""

    def test_discovery_report_success(self, client):
        """Discovery report stores APIs in health_details and returns 200."""
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
                f"/v1/internal/gateways/{gw.id}/discovery",
                json={
                    "apis": [
                        {
                            "name": "echo-service",
                            "version": "1.0",
                            "backend_url": "http://echo:8888",
                            "paths": ["/echo"],
                            "methods": ["GET", "POST"],
                            "policies": ["rate-limiting"],
                            "is_active": True,
                        },
                        {
                            "name": "api-service",
                            "backend_url": "http://api:3000",
                            "is_active": False,
                        },
                    ]
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["apis_received"] == 2
            assert gw.health_details["discovered_apis_count"] == 2
            assert len(gw.health_details["discovered_apis"]) == 2
            assert gw.health_details["discovered_apis"][0]["name"] == "echo-service"

    def test_discovery_report_empty(self, client):
        """Empty discovery report is accepted."""
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
                f"/v1/internal/gateways/{gw.id}/discovery",
                json={"apis": []},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert resp.json()["apis_received"] == 0

    def test_discovery_report_invalid_key(self, client):
        """Discovery with invalid key returns 401."""
        fake_id = uuid4()

        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/discovery",
                json={"apis": []},
                headers={GW_KEY_HEADER: "wrong_key"},
            )

            assert resp.status_code == 401

    def test_discovery_report_not_found(self, client):
        """Discovery for non-existent gateway returns 404."""
        fake_id = uuid4()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/discovery",
                json={"apis": [{"name": "test", "is_active": True}]},
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 404


class TestGatewaySyncAck:
    """POST /v1/internal/gateways/{id}/sync-ack"""

    def test_sync_ack_success(self, client):
        """Sync-ack stores results in health_details."""
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
                f"/v1/internal/gateways/{gw.id}/sync-ack",
                json={
                    "synced_policies": [
                        {"policy_id": "pol-1", "status": "applied"},
                        {"policy_id": "pol-2", "status": "removed"},
                        {"policy_id": "pol-3", "status": "failed", "error": "timeout"},
                    ],
                    "sync_timestamp": "2026-03-15T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["applied"] == 1
            assert data["removed"] == 1
            assert data["failed"] == 1
            assert gw.health_details["last_sync"] == "2026-03-15T12:00:00Z"
            assert gw.health_details["sync_applied"] == 1
            assert gw.health_details["sync_removed"] == 1
            assert gw.health_details["sync_failed"] == 1

    def test_sync_ack_empty(self, client):
        """Empty sync-ack is accepted."""
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
                f"/v1/internal/gateways/{gw.id}/sync-ack",
                json={
                    "synced_policies": [],
                    "sync_timestamp": "2026-03-15T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert resp.json()["applied"] == 0

    def test_sync_ack_invalid_key(self, client):
        """Sync-ack with invalid key returns 401."""
        fake_id = uuid4()

        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/sync-ack",
                json={"synced_policies": [], "sync_timestamp": "2026-03-15T12:00:00Z"},
                headers={GW_KEY_HEADER: "wrong_key"},
            )

            assert resp.status_code == 401

    def test_sync_ack_not_found(self, client):
        """Sync-ack for non-existent gateway returns 404."""
        fake_id = uuid4()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            resp = client.post(
                f"/v1/internal/gateways/{fake_id}/sync-ack",
                json={
                    "synced_policies": [{"policy_id": "pol-1", "status": "applied"}],
                    "sync_timestamp": "2026-03-15T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 404


def _make_deployment(**overrides):
    """Create a mock GatewayDeployment."""
    from src.models.gateway_deployment import DeploymentSyncStatus

    dep_id = overrides.pop("id", uuid4())
    defaults = {
        "id": dep_id,
        "api_catalog_id": uuid4(),
        "gateway_instance_id": uuid4(),
        "sync_status": DeploymentSyncStatus.PENDING,
        "last_sync_attempt": None,
        "last_sync_success": None,
        "sync_error": None,
        "sync_steps": None,
        "sync_attempts": 0,
        "promotion_id": None,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestRouteSyncAck:
    """POST /v1/internal/gateways/{id}/route-sync-ack"""

    def test_route_sync_ack_success(self, client):
        """Two deployments applied → sync_status=SYNCED + last_sync_success set."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        dep1 = _make_deployment()
        dep2 = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value

            async def get_by_id_side_effect(dep_id):
                for d in [dep1, dep2]:
                    if d.id == dep_id:
                        return d
                return None

            mock_deploy_repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            mock_deploy_repo.update = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep1.id), "status": "applied"},
                        {"deployment_id": str(dep2.id), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-03-27T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 2
            assert data["not_found"] == 0
            assert dep1.sync_status == DeploymentSyncStatus.SYNCED
            assert dep1.last_sync_success is not None
            assert dep1.sync_error is None
            assert dep2.sync_status == DeploymentSyncStatus.SYNCED

    def test_route_sync_ack_failed(self, client):
        """One deployment failed → sync_status=ERROR + sync_error set."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        dep = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "failed", "error": "connection refused"},
                    ],
                    "sync_timestamp": "2026-03-27T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 1
            assert dep.sync_status == DeploymentSyncStatus.ERROR
            assert dep.sync_error == "connection refused"

    def test_route_sync_ack_mixed(self, client):
        """One applied + one failed → each updated independently."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        dep_ok = _make_deployment()
        dep_fail = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value

            async def get_by_id_side_effect(dep_id):
                for d in [dep_ok, dep_fail]:
                    if d.id == dep_id:
                        return d
                return None

            mock_deploy_repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            mock_deploy_repo.update = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep_ok.id), "status": "applied"},
                        {"deployment_id": str(dep_fail.id), "status": "failed", "error": "timeout"},
                    ],
                    "sync_timestamp": "2026-03-27T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 2
            assert data["not_found"] == 0
            assert dep_ok.sync_status == DeploymentSyncStatus.SYNCED
            assert dep_ok.sync_error is None
            assert dep_fail.sync_status == DeploymentSyncStatus.ERROR
            assert dep_fail.sync_error == "timeout"

    def test_route_sync_ack_deployment_not_found(self, client):
        """Non-existent deployment_id → 200 with not_found=1 (no crash)."""
        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=None)

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(uuid4()), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-03-27T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["processed"] == 0
            assert data["not_found"] == 1


    def test_route_sync_ack_with_steps_merges_cp_step(self, client):
        """Ack with agent steps → sync_steps includes CP event_emitted + agent steps."""
        dep = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            agent_steps = [
                {"name": "agent_received", "status": "success", "started_at": "2026-04-02T12:00:01Z"},
                {"name": "adapter_connected", "status": "success", "started_at": "2026-04-02T12:00:02Z"},
                {"name": "api_synced", "status": "success", "started_at": "2026-04-02T12:00:03Z"},
            ]

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "applied", "steps": agent_steps},
                    ],
                    "sync_timestamp": "2026-04-02T12:00:04Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep.sync_steps is not None
            assert len(dep.sync_steps) == 4  # event_emitted + 3 agent steps
            assert dep.sync_steps[0]["name"] == "event_emitted"
            assert dep.sync_steps[0]["status"] == "success"
            assert dep.sync_steps[1]["name"] == "agent_received"
            assert dep.sync_steps[2]["name"] == "adapter_connected"
            assert dep.sync_steps[3]["name"] == "api_synced"

    def test_route_sync_ack_without_steps_backward_compat(self, client):
        """Ack without steps field → sync_steps stays None (old agent compat)."""
        dep = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-04-02T12:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep.sync_steps is None

    def test_route_sync_ack_failed_with_steps_derives_error(self, client):
        """Ack with failed step → sync_error derived from step trace."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        dep = _make_deployment()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            agent_steps = [
                {"name": "agent_received", "status": "success", "started_at": "2026-04-02T12:00:01Z"},
                {"name": "adapter_connected", "status": "success", "started_at": "2026-04-02T12:00:02Z"},
                {"name": "api_synced", "status": "failed", "started_at": "2026-04-02T12:00:03Z", "detail": "connection refused"},
            ]

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "failed", "error": "sync error", "steps": agent_steps},
                    ],
                    "sync_timestamp": "2026-04-02T12:00:04Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep.sync_status == DeploymentSyncStatus.ERROR
            assert dep.sync_error == "connection refused"


class TestHelperFunctions:
    """Unit tests for internal helper functions."""

    def test_derive_instance_name(self):
        """Instance name is deterministic: hostname-mode-environment."""
        from src.routers.gateway_internal import _derive_instance_name

        assert _derive_instance_name("gw-abc", "edge_mcp", "prod") == "gw-abc-edgemcp-prod"
        assert _derive_instance_name("gw-xyz", "sidecar", "dev") == "gw-xyz-sidecar-dev"

    def test_mode_to_gateway_type(self):
        """Mode strings map to correct GatewayType enum values."""
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type

        assert _mode_to_gateway_type("edge-mcp") == GatewayType.STOA_EDGE_MCP
        assert _mode_to_gateway_type("edge_mcp") == GatewayType.STOA_EDGE_MCP
        assert _mode_to_gateway_type("sidecar") == GatewayType.STOA_SIDECAR
        assert _mode_to_gateway_type("connect") == GatewayType.STOA
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
        assert _normalize_mode("connect") == "connect"
        assert _normalize_mode("unknown") == "edge-mcp"  # default fallback

    def test_regression_connect_mode_not_fallthrough(self):
        """Regression: connect mode must NOT fall through to edge-mcp (CAB-1819).

        Root cause: _normalize_mode had no "connect" entry, so it fell through
        to the default "edge-mcp", misrepresenting all stoa-connect agents.
        """
        from src.models.gateway_instance import GatewayType
        from src.routers.gateway_internal import _mode_to_gateway_type, _normalize_mode

        # connect must be preserved as-is, not mapped to edge-mcp
        assert _normalize_mode("connect") == "connect"
        assert _normalize_mode("connect") != "edge-mcp"

        # connect maps to GatewayType.STOA (bridge agent, not a new adapter type)
        assert _mode_to_gateway_type("connect") == GatewayType.STOA


class TestRouteSyncAckPromotionCompletion:
    """Tests for promotion auto-completion triggered by route-sync-ack."""

    def test_route_ack_triggers_promotion_complete(self, client):
        """Single promotion, single gateway — ack applied → promotion PROMOTED."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        promo_id = uuid4()
        dep = _make_deployment(promotion_id=promo_id)

        mock_promotion = MagicMock()
        mock_promotion.id = promo_id
        mock_promotion.status = "promoting"

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.PromotionService") as MockPromoSvc,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            mock_promo_svc = MockPromoSvc.return_value
            mock_promo_svc.check_promotion_completion = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-03-27T14:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep.sync_status == DeploymentSyncStatus.SYNCED
            mock_promo_svc.check_promotion_completion.assert_awaited_once_with(promo_id)

    def test_route_ack_partial_does_not_complete(self, client):
        """1 promotion, 2 gateways, only 1 ack → promotion NOT completed yet."""
        promo_id = uuid4()
        dep1 = _make_deployment(promotion_id=promo_id)
        dep2 = _make_deployment(promotion_id=promo_id)  # Not in the ack payload

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.PromotionService") as MockPromoSvc,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value

            async def get_by_id_side_effect(dep_id):
                if dep_id == dep1.id:
                    return dep1
                return None

            mock_deploy_repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            mock_deploy_repo.update = AsyncMock()

            mock_promo_svc = MockPromoSvc.return_value
            mock_promo_svc.check_promotion_completion = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep1.id), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-03-27T14:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            # check_promotion_completion IS called — the service internally
            # decides whether to complete based on remaining deployments
            mock_promo_svc.check_promotion_completion.assert_awaited_once_with(promo_id)

    def test_route_ack_all_synced_completes(self, client):
        """1 promotion, 2 gateways, 2 acks applied → check called once for the promotion."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        promo_id = uuid4()
        dep1 = _make_deployment(promotion_id=promo_id)
        dep2 = _make_deployment(promotion_id=promo_id)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.PromotionService") as MockPromoSvc,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value

            async def get_by_id_side_effect(dep_id):
                for d in [dep1, dep2]:
                    if d.id == dep_id:
                        return d
                return None

            mock_deploy_repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            mock_deploy_repo.update = AsyncMock()

            mock_promo_svc = MockPromoSvc.return_value
            mock_promo_svc.check_promotion_completion = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep1.id), "status": "applied"},
                        {"deployment_id": str(dep2.id), "status": "applied"},
                    ],
                    "sync_timestamp": "2026-03-27T14:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep1.sync_status == DeploymentSyncStatus.SYNCED
            assert dep2.sync_status == DeploymentSyncStatus.SYNCED
            # Called once — promo_id is deduplicated via set
            mock_promo_svc.check_promotion_completion.assert_awaited_once_with(promo_id)

    def test_route_ack_error_fails_promotion(self, client):
        """1 promotion, 1 gateway, ack failed → check called (service handles failure)."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        promo_id = uuid4()
        dep = _make_deployment(promotion_id=promo_id)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.PromotionService") as MockPromoSvc,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
            mock_deploy_repo.update = AsyncMock()

            mock_promo_svc = MockPromoSvc.return_value
            mock_promo_svc.check_promotion_completion = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep.id), "status": "failed", "error": "timeout"},
                    ],
                    "sync_timestamp": "2026-03-27T14:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep.sync_status == DeploymentSyncStatus.ERROR
            mock_promo_svc.check_promotion_completion.assert_awaited_once_with(promo_id)

    def test_route_ack_mixed_error_and_pending(self, client):
        """1 promotion, 2 gateways, 1 error ack + 1 not yet acked → check called once."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        promo_id = uuid4()
        dep_err = _make_deployment(promotion_id=promo_id)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
            patch("src.routers.gateway_internal.PromotionService") as MockPromoSvc,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=dep_err)
            mock_deploy_repo.update = AsyncMock()

            mock_promo_svc = MockPromoSvc.return_value
            mock_promo_svc.check_promotion_completion = AsyncMock()

            resp = client.post(
                f"/v1/internal/gateways/{uuid4()}/route-sync-ack",
                json={
                    "synced_routes": [
                        {"deployment_id": str(dep_err.id), "status": "failed", "error": "connection refused"},
                    ],
                    "sync_timestamp": "2026-03-27T14:00:00Z",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

            assert resp.status_code == 200
            assert dep_err.sync_status == DeploymentSyncStatus.ERROR
            # check is called — the service will see 1 ERROR + 1 PENDING still remaining
            # and will NOT complete/fail yet
            mock_promo_svc.check_promotion_completion.assert_awaited_once_with(promo_id)
