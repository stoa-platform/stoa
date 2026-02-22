"""Tests for GatewayAdapterInterface (CAB-1388).

Abstract method `...` bodies are executed by calling each method as an
unbound function on a MagicMock self, so coverage counts those lines.
"""

from unittest.mock import MagicMock

from src.adapters.gateway_adapter_interface import AdapterResult, GatewayAdapterInterface

# ── AdapterResult ──


class TestAdapterResult:
    def test_success_defaults(self):
        result = AdapterResult(success=True)
        assert result.success is True
        assert result.resource_id is None
        assert result.data == {}
        assert result.error is None

    def test_failure_with_all_fields(self):
        result = AdapterResult(success=False, resource_id="r-1", data={"k": "v"}, error="oops")
        assert result.success is False
        assert result.resource_id == "r-1"
        assert result.data == {"k": "v"}
        assert result.error == "oops"

    def test_data_field_default_is_independent(self):
        r1 = AdapterResult(success=True)
        r2 = AdapterResult(success=True)
        r1.data["x"] = 1
        assert "x" not in r2.data


# ── Abstract method bodies ──


class TestAbstractMethodBodies:
    """Execute the `...` body of each abstract method via unbound call."""

    async def test_health_check_body(self):
        result = await GatewayAdapterInterface.health_check(MagicMock())
        assert result is None

    async def test_connect_body(self):
        result = await GatewayAdapterInterface.connect(MagicMock())
        assert result is None

    async def test_disconnect_body(self):
        result = await GatewayAdapterInterface.disconnect(MagicMock())
        assert result is None

    async def test_sync_api_body(self):
        result = await GatewayAdapterInterface.sync_api(MagicMock(), {}, "t1")
        assert result is None

    async def test_delete_api_body(self):
        result = await GatewayAdapterInterface.delete_api(MagicMock(), "api-1")
        assert result is None

    async def test_list_apis_body(self):
        result = await GatewayAdapterInterface.list_apis(MagicMock())
        assert result is None

    async def test_upsert_policy_body(self):
        result = await GatewayAdapterInterface.upsert_policy(MagicMock(), {})
        assert result is None

    async def test_delete_policy_body(self):
        result = await GatewayAdapterInterface.delete_policy(MagicMock(), "p-1")
        assert result is None

    async def test_list_policies_body(self):
        result = await GatewayAdapterInterface.list_policies(MagicMock())
        assert result is None

    async def test_provision_application_body(self):
        result = await GatewayAdapterInterface.provision_application(MagicMock(), {})
        assert result is None

    async def test_deprovision_application_body(self):
        result = await GatewayAdapterInterface.deprovision_application(MagicMock(), "app-1")
        assert result is None

    async def test_list_applications_body(self):
        result = await GatewayAdapterInterface.list_applications(MagicMock())
        assert result is None

    async def test_upsert_auth_server_body(self):
        result = await GatewayAdapterInterface.upsert_auth_server(MagicMock(), {})
        assert result is None

    async def test_upsert_strategy_body(self):
        result = await GatewayAdapterInterface.upsert_strategy(MagicMock(), {})
        assert result is None

    async def test_upsert_scope_body(self):
        result = await GatewayAdapterInterface.upsert_scope(MagicMock(), {})
        assert result is None

    async def test_upsert_alias_body(self):
        result = await GatewayAdapterInterface.upsert_alias(MagicMock(), {})
        assert result is None

    async def test_apply_config_body(self):
        result = await GatewayAdapterInterface.apply_config(MagicMock(), {})
        assert result is None

    async def test_export_archive_body(self):
        result = await GatewayAdapterInterface.export_archive(MagicMock())
        assert result is None


# ── deploy_contract (concrete default) ──


class TestDeployContract:
    async def test_returns_not_supported_result(self):
        result = await GatewayAdapterInterface.deploy_contract(MagicMock(), {})
        assert isinstance(result, AdapterResult)
        assert result.success is False
        assert result.error is not None
        assert "not supported" in result.error

    async def test_with_auth_token(self):
        result = await GatewayAdapterInterface.deploy_contract(MagicMock(), {}, "tok-123")
        assert result.success is False
