"""Tests for TemplateGatewayAdapter, template mappers, and AdapterResult defaults."""

import pytest

from src.adapters.gateway_adapter_interface import AdapterResult
from src.adapters.template.adapter import TemplateGatewayAdapter
from src.adapters.template.mappers import map_api_from_gateway, map_api_spec, map_policy


# ---------------------------------------------------------------------------
# AdapterResult
# ---------------------------------------------------------------------------


class TestAdapterResult:
    """Tests for the AdapterResult dataclass."""

    def test_success_result(self):
        result = AdapterResult(success=True, resource_id="r-1", data={"k": "v"})
        assert result.success is True
        assert result.resource_id == "r-1"
        assert result.data == {"k": "v"}
        assert result.error is None

    def test_failure_result(self):
        result = AdapterResult(success=False, error="something went wrong")
        assert result.success is False
        assert result.error == "something went wrong"
        assert result.resource_id is None

    def test_default_data_is_empty_dict(self):
        result = AdapterResult(success=True)
        assert result.data == {}

    def test_two_results_with_same_data_are_equal(self):
        r1 = AdapterResult(success=True, resource_id="x")
        r2 = AdapterResult(success=True, resource_id="x")
        assert r1 == r2


# ---------------------------------------------------------------------------
# deploy_contract default implementation
# ---------------------------------------------------------------------------


class TestDeployContractDefault:
    """deploy_contract on TemplateGatewayAdapter uses the interface default."""

    async def test_deploy_contract_returns_not_supported(self):
        adapter = TemplateGatewayAdapter()
        result = await adapter.deploy_contract({"contract": "spec"})
        assert result.success is False
        assert "deploy_contract not supported" in result.error

    async def test_deploy_contract_ignores_auth_token(self):
        adapter = TemplateGatewayAdapter()
        result = await adapter.deploy_contract({}, auth_token="tok")
        assert result.success is False


# ---------------------------------------------------------------------------
# TemplateGatewayAdapter — instantiation
# ---------------------------------------------------------------------------


class TestTemplateAdapterInit:
    """Tests for adapter instantiation."""

    def test_no_config(self):
        adapter = TemplateGatewayAdapter()
        assert adapter._config == {}

    def test_config_stored(self):
        cfg = {"base_url": "http://gw.example.com", "auth_config": {"token": "abc"}}
        adapter = TemplateGatewayAdapter(config=cfg)
        assert adapter._config["base_url"] == "http://gw.example.com"
        assert adapter._config["auth_config"]["token"] == "abc"

    def test_none_config_becomes_empty_dict(self):
        adapter = TemplateGatewayAdapter(config=None)
        assert adapter._config == {}


# ---------------------------------------------------------------------------
# TemplateGatewayAdapter — required methods raise NotImplementedError
# ---------------------------------------------------------------------------


class TestTemplateAdapterRequiredMethods:
    """All 6 required methods must raise NotImplementedError."""

    async def test_connect_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().connect()

    async def test_disconnect_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().disconnect()

    async def test_health_check_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().health_check()

    async def test_sync_api_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().sync_api({"api_name": "test"}, "tenant-1")

    async def test_delete_api_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().delete_api("api-123")

    async def test_list_apis_raises(self):
        with pytest.raises(NotImplementedError):
            await TemplateGatewayAdapter().list_apis()


# ---------------------------------------------------------------------------
# TemplateGatewayAdapter — optional methods return not-supported
# ---------------------------------------------------------------------------


class TestTemplateAdapterOptionalMethods:
    """Optional methods return AdapterResult(success=False) or empty list."""

    async def test_upsert_policy(self):
        result = await TemplateGatewayAdapter().upsert_policy({"name": "cors"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_delete_policy(self):
        result = await TemplateGatewayAdapter().delete_policy("pol-1")
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_list_policies_returns_empty(self):
        result = await TemplateGatewayAdapter().list_policies()
        assert result == []

    async def test_provision_application(self):
        result = await TemplateGatewayAdapter().provision_application({"app": "x"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_deprovision_application(self):
        result = await TemplateGatewayAdapter().deprovision_application("app-1")
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_list_applications_returns_empty(self):
        result = await TemplateGatewayAdapter().list_applications()
        assert result == []

    async def test_upsert_auth_server(self):
        result = await TemplateGatewayAdapter().upsert_auth_server({"name": "keycloak"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_upsert_strategy(self):
        result = await TemplateGatewayAdapter().upsert_strategy({"name": "oauth2"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_upsert_scope(self):
        result = await TemplateGatewayAdapter().upsert_scope({"scopeName": "read"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_upsert_alias(self):
        result = await TemplateGatewayAdapter().upsert_alias({"name": "backend"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_apply_config(self):
        result = await TemplateGatewayAdapter().apply_config({"jwt_issuer": "kc"})
        assert result.success is False
        assert result.error == "Not supported by this gateway"

    async def test_export_archive_returns_empty_bytes(self):
        result = await TemplateGatewayAdapter().export_archive()
        assert result == b""

    async def test_optional_methods_accept_positional_auth_token(self):
        """auth_token positional arg does not raise on optional methods."""
        adapter = TemplateGatewayAdapter()
        result = await adapter.upsert_policy({"name": "cors"}, "tok")
        assert result.success is False
        result = await adapter.delete_policy("p-1", "tok")
        assert result.success is False
        policies = await adapter.list_policies("tok")
        assert policies == []
        data = await adapter.export_archive("tok")
        assert data == b""


# ---------------------------------------------------------------------------
# map_api_spec
# ---------------------------------------------------------------------------


class TestMapApiSpec:
    """Tests for map_api_spec mapper."""

    def test_full_spec(self):
        result = map_api_spec(
            api_spec={
                "api_name": "Payments",
                "version": "2.1.0",
                "spec_hash": "sha256-abc",
                "api_id": "cat-1",
                "activated": True,
            },
            tenant_id="acme",
        )
        assert result["name"] == "Payments"
        assert result["version"] == "2.1.0"

    def test_missing_fields_default_to_empty_string(self):
        result = map_api_spec(api_spec={}, tenant_id="acme")
        assert result["name"] == ""
        assert result["version"] == ""

    def test_tenant_id_accepted(self):
        """tenant_id parameter is accepted without error."""
        result = map_api_spec({"api_name": "Test"}, "tenant-xyz")
        assert result["name"] == "Test"

    def test_returns_dict(self):
        result = map_api_spec({"api_name": "X", "version": "1"}, "t")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# map_policy
# ---------------------------------------------------------------------------


class TestMapPolicy:
    """Tests for map_policy mapper."""

    def test_full_policy(self):
        result = map_policy(
            {
                "name": "rate-limit-100",
                "type": "rate_limit",
                "config": {"rate": 100, "window": "1m"},
            }
        )
        assert result["name"] == "rate-limit-100"
        assert result["type"] == "rate_limit"
        assert result["config"] == {"rate": 100, "window": "1m"}

    def test_missing_fields_default_to_empty(self):
        result = map_policy({})
        assert result["name"] == ""
        assert result["type"] == ""
        assert result["config"] == {}

    def test_config_nested_dict_preserved(self):
        cfg = {"rate": 50, "burst": 10, "nested": {"key": "val"}}
        result = map_policy({"config": cfg})
        assert result["config"] == cfg

    def test_cors_policy(self):
        result = map_policy(
            {
                "name": "cors-policy",
                "type": "cors",
                "config": {"origins": ["https://example.com"]},
            }
        )
        assert result["type"] == "cors"
        assert result["config"]["origins"] == ["https://example.com"]


# ---------------------------------------------------------------------------
# map_api_from_gateway
# ---------------------------------------------------------------------------


class TestMapApiFromGateway:
    """Tests for map_api_from_gateway mapper."""

    def test_full_gateway_api(self):
        result = map_api_from_gateway(
            {"id": "gw-api-1", "name": "payments", "spec_hash": "sha256-xyz"}
        )
        assert result["id"] == "gw-api-1"
        assert result["name"] == "payments"
        assert result["spec_hash"] == "sha256-xyz"

    def test_missing_fields_default_to_empty_string(self):
        result = map_api_from_gateway({})
        assert result["id"] == ""
        assert result["name"] == ""
        assert result["spec_hash"] == ""

    def test_extra_gateway_fields_not_in_output(self):
        result = map_api_from_gateway(
            {
                "id": "gw-1",
                "name": "test",
                "spec_hash": "abc",
                "internal_field": "ignored",
            }
        )
        assert "internal_field" not in result

    def test_returns_dict_with_expected_keys(self):
        result = map_api_from_gateway({"id": "x", "name": "y", "spec_hash": "z"})
        assert set(result.keys()) == {"id", "name", "spec_hash"}
