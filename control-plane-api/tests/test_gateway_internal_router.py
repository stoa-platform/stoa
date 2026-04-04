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
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
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
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=None)
            mock_repo.find_self_registered_by_mode_env = AsyncMock(return_value=[])
            mock_repo.get_by_source_and_type = AsyncMock(return_value=None)
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
# Regression: register after soft-delete (CAB-1937)
# ---------------------------------------------------------------------------


class TestRegressionRegisterAfterSoftDelete:
    """POST /register must resurrect a soft-deleted entry instead of 409."""

    def test_regression_register_after_soft_delete(self, client):
        """Gateway re-registration after auto-purge resurrects the soft-deleted entry."""
        deleted_gw = _make_gateway_instance(
            deleted_at=datetime(2026, 3, 30, tzinfo=UTC),
            deleted_by="auto-purge",
            status=MagicMock(value="offline"),
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=deleted_gw)
            mock_repo.update = AsyncMock(return_value=deleted_gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "gw-host",
                    "mode": "edge-mcp",
                    "version": "0.3.0",
                    "environment": "staging",
                    "admin_url": "http://gw:8080",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201
        mock_repo.create.assert_not_called()
        mock_repo.update.assert_awaited_once()
        assert deleted_gw.deleted_at is None
        assert deleted_gw.deleted_by is None
        assert deleted_gw.version == "0.3.0"

    def test_regression_register_soft_deleted_skips_cancel_and_replace(self, client):
        """Resurrection path should not reach cancel-and-replace or create steps."""
        deleted_gw = _make_gateway_instance(
            deleted_at=datetime(2026, 3, 30, tzinfo=UTC),
            deleted_by="replaced-by:other-gw",
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.get_by_name_including_deleted = AsyncMock(return_value=deleted_gw)
            mock_repo.update = AsyncMock(return_value=deleted_gw)

            resp = client.post(
                REGISTER_URL,
                json={
                    "hostname": "gw-host",
                    "mode": "edge-mcp",
                    "version": "0.2.0",
                    "environment": "staging",
                    "admin_url": "http://gw:8080",
                },
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 201
        mock_repo.find_self_registered_by_mode_env.assert_not_called()
        mock_repo.get_by_source_and_type.assert_not_called()
        mock_repo.create.assert_not_called()


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


# ---------------------------------------------------------------------------
# Internal tool discovery — GET /v1/internal/gateways/tools
# ---------------------------------------------------------------------------


def _make_tool(
    tool_name: str = "acme__payment-api__charge",
    description: str = "Charge a card",
    input_schema: str | None = '{"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]}',
    output_schema: str | None = None,
    backend_url: str = "https://api.acme.com",
    http_method: str = "POST",
    path_pattern: str = "/charge",
    version: str = "1.0.0",
    spec_hash: str | None = "abc123",
    enabled: bool = True,
) -> MagicMock:
    """Build a minimal McpGeneratedTool-like mock."""
    m = MagicMock()
    m.tool_name = tool_name
    m.description = description
    m.input_schema = input_schema
    m.output_schema = output_schema
    m.backend_url = backend_url
    m.http_method = http_method
    m.path_pattern = path_pattern
    m.version = version
    m.spec_hash = spec_hash
    m.enabled = enabled
    return m


class TestInternalToolDiscovery:
    """GET /v1/internal/gateways/tools — internal tool discovery for gateway sidecars."""

    # --- /tools ---

    def test_tools_returns_401_without_key(self, client):
        """Missing X-Gateway-Key header returns 422 (FastAPI required header validation)."""
        resp = client.get("/v1/internal/gateways/tools?tenant_id=acme")
        # FastAPI rejects missing required Header(...) with 422 Unprocessable Entity
        assert resp.status_code == 422

    def test_tools_returns_401_with_invalid_key(self, client):
        """Wrong X-Gateway-Key returns 401."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: "wrong-key"},
            )
        assert resp.status_code == 401

    def test_tools_returns_503_when_no_keys_configured(self, client):
        """Empty GATEWAY_API_KEYS returns 503."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = []
            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )
        assert resp.status_code == 503

    def test_tools_returns_empty_without_tenant(self, client):
        """No tenant_id query param returns empty tools list (default="" short-circuit)."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            resp = client.get(
                "/v1/internal/gateways/tools",
                headers={GW_KEY_HEADER: VALID_KEY},
            )
        assert resp.status_code == 200
        assert resp.json() == {"tools": []}

    def test_tools_returns_tools_for_tenant(self, client):
        """Valid key + tenant_id returns enabled tools in ToolsListResponse format."""
        tool = _make_tool()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_instance = MockGenerator.return_value
            mock_instance.get_tools_for_tenant = AsyncMock(return_value=[tool])

            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["tools"]) == 1
        assert body["tools"][0]["name"] == tool.tool_name
        assert body["tools"][0]["description"] == tool.description
        assert "inputSchema" in body["tools"][0]

    def test_tools_skips_disabled_tools(self, client):
        """Disabled tools are excluded from the response."""
        enabled_tool = _make_tool(tool_name="active-tool", enabled=True)
        disabled_tool = _make_tool(tool_name="disabled-tool", enabled=False)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_instance = MockGenerator.return_value
            mock_instance.get_tools_for_tenant = AsyncMock(
                return_value=[enabled_tool, disabled_tool]
            )

            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["tools"]]
        assert "active-tool" in names
        assert "disabled-tool" not in names

    def test_tools_parses_input_schema_json(self, client):
        """input_schema string is parsed into the inputSchema object."""
        tool = _make_tool(
            input_schema='{"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}'
        )

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockGenerator.return_value.get_tools_for_tenant = AsyncMock(return_value=[tool])

            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        schema = resp.json()["tools"][0]["inputSchema"]
        assert schema["type"] == "object"
        assert "q" in schema["properties"]

    def test_tools_uses_default_schema_when_input_schema_is_none(self, client):
        """Tool with no input_schema gets a default empty object schema."""
        tool = _make_tool(input_schema=None)

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockGenerator.return_value.get_tools_for_tenant = AsyncMock(return_value=[tool])

            resp = client.get(
                "/v1/internal/gateways/tools?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        schema = resp.json()["tools"][0]["inputSchema"]
        assert schema == {"type": "object", "properties": {}, "required": []}

    # --- /tools/generated ---

    def test_generated_tools_returns_401_without_key(self, client):
        """Missing X-Gateway-Key header returns 422 for /tools/generated."""
        resp = client.get("/v1/internal/gateways/tools/generated?tenant_id=acme")
        assert resp.status_code == 422

    def test_generated_tools_returns_401_with_invalid_key(self, client):
        """Wrong X-Gateway-Key returns 401 for /tools/generated."""
        with patch("src.routers.gateway_internal.settings") as mock_settings:
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            resp = client.get(
                "/v1/internal/gateways/tools/generated?tenant_id=acme",
                headers={GW_KEY_HEADER: "bad-key"},
            )
        assert resp.status_code == 401

    def test_generated_tools_returns_tools_for_tenant(self, client):
        """Valid key + tenant_id returns TenantToolsResponse format."""
        tool = _make_tool()

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            mock_instance = MockGenerator.return_value
            mock_instance.get_tools_for_tenant = AsyncMock(return_value=[tool])

            resp = client.get(
                "/v1/internal/gateways/tools/generated?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "acme"
        assert body["total"] == 1
        assert len(body["tools"]) == 1
        assert body["tools"][0]["tool_name"] == tool.tool_name

    def test_generated_tools_returns_empty_list_for_unknown_tenant(self, client):
        """Tenant with no tools returns TenantToolsResponse with empty list."""
        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockGenerator.return_value.get_tools_for_tenant = AsyncMock(return_value=[])

            resp = client.get(
                "/v1/internal/gateways/tools/generated?tenant_id=unknown-tenant",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "unknown-tenant"
        assert body["total"] == 0
        assert body["tools"] == []

    def test_generated_tools_total_matches_tools_length(self, client):
        """total field in TenantToolsResponse matches the actual number of tools."""
        tools = [
            _make_tool(tool_name=f"tool-{i}") for i in range(3)
        ]

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.UacToolGenerator") as MockGenerator,
        ):
            mock_settings.gateway_api_keys_list = [VALID_KEY]
            MockGenerator.return_value.get_tools_for_tenant = AsyncMock(return_value=tools)

            resp = client.get(
                "/v1/internal/gateways/tools/generated?tenant_id=acme",
                headers={GW_KEY_HEADER: VALID_KEY},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["tools"]) == 3


# ---------------------------------------------------------------------------
# Routes endpoint — GET /v1/internal/gateways/routes (CAB-1929)
# ---------------------------------------------------------------------------


def _make_deployment(desired_state: dict):
    """Build a minimal mock GatewayDeployment."""
    m = MagicMock()
    m.desired_state = desired_state
    return m


class TestListGatewayRoutes:
    """GET /v1/internal/gateways/routes — outbound-only route delivery (CAB-1929)."""

    def test_routes_returns_basic_fields(self, client):
        """Route with no openapi_spec returns standard fields."""
        dep = _make_deployment({
            "api_catalog_id": "cat-1",
            "api_name": "petstore",
            "backend_url": "http://petstore:8080",
            "methods": ["GET", "POST"],
            "spec_hash": "abc123",
            "activated": True,
            "tenant_id": "tenant-a",
        })

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockRepo,
        ):
            mock_settings.GATEWAY_ADMIN_KEY = None
            MockRepo.return_value.list_by_statuses = AsyncMock(return_value=[dep])

            resp = client.get("/v1/internal/gateways/routes")

        assert resp.status_code == 200
        routes = resp.json()
        assert len(routes) == 1
        assert routes[0]["name"] == "petstore"
        assert routes[0]["spec_hash"] == "abc123"
        assert routes[0]["openapi_spec"] is None

    def test_regression_openapi_spec_dict_delivered_to_connect(self, client):
        """openapi_spec dict in desired_state is delivered as JSON object to stoa-connect.

        CAB-1929: outbound-only model — CP delivers spec as a dict so stoa-connect
        can push it to the on-premise gateway without any inbound call-back.
        webMethods requires apiDefinition as a JSON object (not a string).
        """
        spec_dict = {"openapi": "3.1.0", "info": {"title": "Petstore", "version": "1.0.0"}}
        dep = _make_deployment({
            "api_catalog_id": "cat-2",
            "api_name": "petstore-spec",
            "backend_url": "http://petstore:8080",
            "methods": ["GET"],
            "spec_hash": "sha-xyz",
            "activated": True,
            "tenant_id": "tenant-b",
            "openapi_spec": spec_dict,
        })

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockRepo,
        ):
            mock_settings.GATEWAY_ADMIN_KEY = None
            MockRepo.return_value.list_by_statuses = AsyncMock(return_value=[dep])

            resp = client.get("/v1/internal/gateways/routes")

        assert resp.status_code == 200
        routes = resp.json()
        assert len(routes) == 1

        # openapi_spec is a JSON object (dict), not a string or base64
        spec = routes[0]["openapi_spec"]
        assert spec is not None, "openapi_spec must be present"
        assert isinstance(spec, dict), f"Expected dict, got {type(spec)}"
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "Petstore"

    def test_routes_skips_deployment_without_backend_url(self, client):
        """Deployments with no backend_url are excluded from the route list."""
        dep = _make_deployment({
            "api_catalog_id": "cat-3",
            "api_name": "no-backend",
            "backend_url": "",
            "tenant_id": "tenant-a",
        })

        with (
            patch("src.routers.gateway_internal.settings") as mock_settings,
            patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockRepo,
        ):
            mock_settings.GATEWAY_ADMIN_KEY = None
            MockRepo.return_value.list_by_statuses = AsyncMock(return_value=[dep])

            resp = client.get("/v1/internal/gateways/routes")

        assert resp.status_code == 200
        assert resp.json() == []
