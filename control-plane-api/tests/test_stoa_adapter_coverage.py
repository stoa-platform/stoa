"""Tests for StoaGatewayAdapter — coverage gap filler.

Covers: health_check, connect/disconnect, sync_api, delete_api, list_apis,
        upsert_policy, delete_policy, list_policies, provision_application,
        deprovision_application, deploy_contract, delete_contract,
        sync_consumer_credentials, unsupported methods.

Existing test_stoa_adapter.py tests the adapter via the registry; these tests
target the methods directly to cover the 59% → ~95% gap.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapters.stoa.adapter import StoaGatewayAdapter


def _adapter(config=None) -> StoaGatewayAdapter:
    cfg = config or {"base_url": "http://gw:8080", "auth_config": {"admin_token": "tok"}}
    return StoaGatewayAdapter(config=cfg)


class TestInit:
    def test_defaults_without_config(self):
        adapter = StoaGatewayAdapter()
        assert adapter._base_url == "http://localhost:8080"
        assert adapter._admin_token == ""

    def test_reads_config(self):
        adapter = _adapter()
        assert adapter._base_url == "http://gw:8080"
        assert adapter._admin_token == "tok"


class TestAuthHeaders:
    def test_with_token(self):
        adapter = _adapter()
        assert adapter._auth_headers() == {"Authorization": "Bearer tok"}

    def test_without_token(self):
        adapter = StoaGatewayAdapter(config={"base_url": "http://gw:8080", "auth_config": {}})
        assert adapter._auth_headers() == {}


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        adapter = _adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.aclose = AsyncMock()
            MockClient.return_value = instance

            result = await adapter.health_check()

        assert result.success is True
        assert result.data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unhealthy_status(self):
        adapter = _adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.aclose = AsyncMock()
            MockClient.return_value = instance

            result = await adapter.health_check()

        assert result.success is False
        assert "503" in result.error

    @pytest.mark.asyncio
    async def test_connection_error(self):
        adapter = _adapter()

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            instance.aclose = AsyncMock()
            MockClient.return_value = instance

            result = await adapter.health_check()

        assert result.success is False

    @pytest.mark.asyncio
    async def test_uses_existing_client(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"status": "ok"}
        adapter._client.get = AsyncMock(return_value=mock_resp)

        result = await adapter.health_check()

        assert result.success is True
        # Should not close the existing client
        adapter._client.aclose.assert_not_called()


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        adapter = _adapter()
        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value = MagicMock()
            await adapter.connect()
        assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        adapter = _adapter()
        mock_client = AsyncMock()
        adapter._client = mock_client
        await adapter.disconnect()
        mock_client.aclose.assert_awaited_once()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_without_client(self):
        adapter = _adapter()
        adapter._client = None
        await adapter.disconnect()  # Should not raise


class TestSyncApi:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=200, text="")
        mock_resp.json.return_value = {"id": "route-1"}
        adapter._client.post = AsyncMock(return_value=mock_resp)

        with patch("src.adapters.stoa.adapter.mappers.map_api_spec_to_stoa", return_value={"id": "route-1", "spec_hash": "abc"}):
            result = await adapter.sync_api({"name": "test"}, "acme")

        assert result.success is True
        assert result.resource_id == "route-1"

    @pytest.mark.asyncio
    async def test_failure_status(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=500, text="Internal error")
        adapter._client.post = AsyncMock(return_value=mock_resp)

        with patch("src.adapters.stoa.adapter.mappers.map_api_spec_to_stoa", return_value={"id": "r"}):
            result = await adapter.sync_api({}, "acme")

        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_exception(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(side_effect=Exception("network"))

        with patch("src.adapters.stoa.adapter.mappers.map_api_spec_to_stoa", return_value={}):
            result = await adapter.sync_api({}, "acme")

        assert result.success is False
        assert "network" in result.error


class TestDeleteApi:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=204))

        result = await adapter.delete_api("api-1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_already_deleted_404(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=404))

        result = await adapter.delete_api("api-1")
        assert result.success is True  # Idempotent

    @pytest.mark.asyncio
    async def test_error_status(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=500))

        result = await adapter.delete_api("api-1")
        assert result.success is False


class TestListApis:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = [{"id": "1"}, {"id": "2"}]
        adapter._client.get = AsyncMock(return_value=mock_resp)

        result = await adapter.list_apis()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_error_returns_empty(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(side_effect=Exception("fail"))

        result = await adapter.list_apis()
        assert result == []


class TestPolicies:
    @pytest.mark.asyncio
    async def test_upsert_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=201, text="")
        mock_resp.json.return_value = {"id": "pol-1"}
        adapter._client.post = AsyncMock(return_value=mock_resp)

        with patch("src.adapters.stoa.adapter.mappers.map_policy_to_stoa", return_value={"id": "pol-1"}):
            result = await adapter.upsert_policy({"type": "rate_limit"})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_upsert_failure(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(return_value=MagicMock(status_code=400, text="bad"))

        with patch("src.adapters.stoa.adapter.mappers.map_policy_to_stoa", return_value={}):
            result = await adapter.upsert_policy({})

        assert result.success is False

    @pytest.mark.asyncio
    async def test_delete_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=200))

        result = await adapter.delete_policy("pol-1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_404_idempotent(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=404))

        result = await adapter.delete_policy("pol-1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_list_policies(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = [{"id": "pol-1"}]
        adapter._client.get = AsyncMock(return_value=mock_resp)

        result = await adapter.list_policies()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_policies_error(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(side_effect=Exception("err"))

        result = await adapter.list_policies()
        assert result == []


class TestProvisionApplication:
    @pytest.mark.asyncio
    async def test_provision_success_with_quota(self):
        adapter = _adapter()
        adapter._client = AsyncMock()

        # sync_api response
        sync_resp = MagicMock(status_code=200, text="")
        sync_resp.json.return_value = {"id": "route-1"}
        # upsert_policy response
        policy_resp = MagicMock(status_code=201, text="")
        policy_resp.json.return_value = {"id": "pol-1"}

        adapter._client.post = AsyncMock(side_effect=[sync_resp, policy_resp])

        with (
            patch("src.adapters.stoa.adapter.mappers.map_app_spec_to_route", return_value={"id": "route-1"}),
            patch("src.adapters.stoa.adapter.mappers.map_api_spec_to_stoa", return_value={"id": "route-1"}),
            patch("src.adapters.stoa.adapter.mappers.map_quota_to_policy", return_value={"id": "pol-1", "type": "rate_limit"}),
            patch("src.adapters.stoa.adapter.mappers.map_policy_to_stoa", return_value={"id": "pol-1"}),
        ):
            result = await adapter.provision_application({"tenant_id": "acme", "api_id": "api-1", "subscription_id": "sub-1"})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_provision_sync_api_failure(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(return_value=MagicMock(status_code=500, text="err"))

        with (
            patch("src.adapters.stoa.adapter.mappers.map_app_spec_to_route", return_value={}),
            patch("src.adapters.stoa.adapter.mappers.map_api_spec_to_stoa", return_value={}),
        ):
            result = await adapter.provision_application({"tenant_id": "acme"})

        assert result.success is False

    @pytest.mark.asyncio
    async def test_deprovision(self):
        adapter = _adapter()
        result = await adapter.deprovision_application("app-1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_list_applications_empty(self):
        adapter = _adapter()
        result = await adapter.list_applications()
        assert result == []


class TestContracts:
    @pytest.mark.asyncio
    async def test_deploy_contract_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=201, text="")
        mock_resp.json.return_value = {"name": "my-contract"}
        adapter._client.post = AsyncMock(return_value=mock_resp)

        with patch("src.adapters.stoa.adapter.mappers.map_uac_to_stoa_contract", return_value={"name": "my-contract"}):
            result = await adapter.deploy_contract({"name": "my-contract"})

        assert result.success is True
        assert result.resource_id == "my-contract"

    @pytest.mark.asyncio
    async def test_deploy_contract_failure(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(return_value=MagicMock(status_code=400, text="bad spec"))

        with patch("src.adapters.stoa.adapter.mappers.map_uac_to_stoa_contract", return_value={}):
            result = await adapter.deploy_contract({})

        assert result.success is False

    @pytest.mark.asyncio
    async def test_delete_contract_success(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=204))

        result = await adapter.delete_contract("my-contract")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_contract_404(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=404))

        result = await adapter.delete_contract("missing")
        assert result.success is True  # Idempotent

    @pytest.mark.asyncio
    async def test_delete_contract_error(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.delete = AsyncMock(return_value=MagicMock(status_code=500))

        result = await adapter.delete_contract("bad")
        assert result.success is False


class TestSyncConsumerCredentials:
    @pytest.mark.asyncio
    async def test_all_succeed(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(return_value=MagicMock(status_code=200))

        mappings = [
            {"consumer_id": "c1", "route_id": "r1"},
            {"consumer_id": "c2", "route_id": "r2"},
        ]
        result = await adapter.sync_consumer_credentials(mappings)

        assert result.success is True
        assert result.data["synced"] == 2

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(
            side_effect=[MagicMock(status_code=200), MagicMock(status_code=500)]
        )

        mappings = [
            {"consumer_id": "c1", "route_id": "r1"},
            {"consumer_id": "c2", "route_id": "r2"},
        ]
        result = await adapter.sync_consumer_credentials(mappings)

        assert result.success is False
        assert result.data["synced"] == 1

    @pytest.mark.asyncio
    async def test_exception_in_one(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        adapter._client.post = AsyncMock(side_effect=[MagicMock(status_code=200), Exception("net err")])

        mappings = [
            {"consumer_id": "c1", "route_id": "r1"},
            {"consumer_id": "c2", "route_id": "r2"},
        ]
        result = await adapter.sync_consumer_credentials(mappings)

        assert result.success is False
        assert "net err" in result.error


class TestUnsupportedMethods:
    @pytest.mark.asyncio
    async def test_auth_server(self):
        result = await _adapter().upsert_auth_server({})
        assert result.success is False
        assert "Not supported" in result.error

    @pytest.mark.asyncio
    async def test_strategy(self):
        result = await _adapter().upsert_strategy({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_scope(self):
        result = await _adapter().upsert_scope({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_alias(self):
        result = await _adapter().upsert_alias({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_config(self):
        result = await _adapter().apply_config({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_export(self):
        result = await _adapter().export_archive()
        assert result == b""


class TestUpdateQuotaPolicy:
    @pytest.mark.asyncio
    async def test_no_quota_needed(self):
        adapter = _adapter()
        with patch("src.adapters.stoa.adapter.mappers.map_quota_to_policy", return_value=None):
            result = await adapter.update_quota_policy({}, "sub-1")
        assert result.success is True
        assert "No quota" in result.data["detail"]

    @pytest.mark.asyncio
    async def test_with_quota(self):
        adapter = _adapter()
        adapter._client = AsyncMock()
        mock_resp = MagicMock(status_code=200, text="")
        mock_resp.json.return_value = {"id": "pol-1"}
        adapter._client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.adapters.stoa.adapter.mappers.map_quota_to_policy", return_value={"type": "rate_limit"}),
            patch("src.adapters.stoa.adapter.mappers.map_policy_to_stoa", return_value={"id": "pol-1"}),
        ):
            result = await adapter.update_quota_policy({}, "sub-1")
        assert result.success is True
