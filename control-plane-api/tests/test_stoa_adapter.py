"""Tests for STOA Gateway Adapter — Python side (Sub-phase 4a)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.gateway_adapter_interface import AdapterResult
from src.adapters.stoa.adapter import StoaGatewayAdapter
from src.adapters.stoa.mappers import map_api_spec_to_stoa, map_policy_to_stoa


class TestStoaAdapterLifecycle:
    """Tests for adapter connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        """connect() initializes an httpx.AsyncClient."""
        adapter = StoaGatewayAdapter(
            config={
                "base_url": "http://localhost:8080",
                "auth_config": {"admin_token": "test-token"},
            }
        )
        assert adapter._client is None

        with patch("src.adapters.stoa.adapter.httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            await adapter.connect()

            assert adapter._client is mock_client
            mock_cls.assert_called_once()
            # Verify auth header is set
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        """disconnect() closes and clears the client."""
        adapter = StoaGatewayAdapter(config={"base_url": "http://localhost:8080"})
        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.disconnect()

        mock_client.aclose.assert_awaited_once()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_no_client(self):
        """disconnect() is safe to call when not connected."""
        adapter = StoaGatewayAdapter()
        await adapter.disconnect()  # Should not raise


class TestStoaAdapterAPIs:
    """Tests for API sync/delete/list operations."""

    def _make_adapter(self):
        adapter = StoaGatewayAdapter(
            config={
                "base_url": "http://gw.test:8080",
                "auth_config": {"admin_token": "secret"},
            }
        )
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_sync_api_success(self):
        """sync_api sends POST /admin/apis and returns success."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "api-123", "status": "ok"}
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            api_spec={"api_name": "payments", "spec_hash": "abc123", "url": "https://backend.com"},
            tenant_id="acme",
        )

        assert result.success is True
        assert result.resource_id == "api-123"
        assert result.data == {"spec_hash": "abc123"}
        client.post.assert_awaited_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/admin/apis"
        payload = call_args[1]["json"]
        assert payload["name"] == "payments"
        assert payload["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_sync_api_failure(self):
        """sync_api returns error on HTTP 500."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal server error"
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.sync_api(
            api_spec={"api_name": "test"},
            tenant_id="acme",
        )

        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_delete_api_success(self):
        """delete_api sends DELETE /admin/apis/{id} and returns success."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        client.delete = AsyncMock(return_value=mock_resp)

        result = await adapter.delete_api("api-123")

        assert result.success is True
        assert result.resource_id == "api-123"
        client.delete.assert_awaited_once_with("/admin/apis/api-123")

    @pytest.mark.asyncio
    async def test_delete_api_404_is_idempotent(self):
        """delete_api returns success on 404 (already deleted)."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client.delete = AsyncMock(return_value=mock_resp)

        result = await adapter.delete_api("api-gone")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_list_apis(self):
        """list_apis returns parsed JSON array."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "api-1", "name": "payments", "spec_hash": "abc"},
            {"id": "api-2", "name": "users", "spec_hash": "def"},
        ]
        client.get = AsyncMock(return_value=mock_resp)

        result = await adapter.list_apis()

        assert len(result) == 2
        assert result[0]["name"] == "payments"


class TestStoaAdapterPolicies:
    """Tests for policy upsert/delete/list operations."""

    def _make_adapter(self):
        adapter = StoaGatewayAdapter(
            config={
                "base_url": "http://gw.test:8080",
                "auth_config": {"admin_token": "secret"},
            }
        )
        mock_client = AsyncMock()
        adapter._client = mock_client
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_upsert_policy(self):
        """upsert_policy sends POST /admin/policies and returns success."""
        adapter, client = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "pol-1", "status": "ok"}
        client.post = AsyncMock(return_value=mock_resp)

        result = await adapter.upsert_policy(
            {
                "name": "rate-limit-100",
                "type": "rate_limit",
                "config": {"rate": 100},
                "priority": 50,
                "api_id": "api-123",
            }
        )

        assert result.success is True
        assert result.resource_id == "pol-1"


class TestStoaAdapterUnsupported:
    """Tests for methods not supported by stoa-gateway."""

    @pytest.mark.asyncio
    async def test_unsupported_methods(self):
        """Methods not supported by stoa-gateway return failure."""
        adapter = StoaGatewayAdapter()

        # Applications — provision_application now implemented (CAB-1121 Phase 3)
        # Without a connected client, sync_api fails gracefully
        result = await adapter.provision_application({"app": "test", "tenant_id": "t"})
        assert result.success is False  # Fails because no client connected

        # deprovision_application now returns success (route kept for other subs)
        result = await adapter.deprovision_application("app-1")
        assert result.success is True

        apps = await adapter.list_applications()
        assert apps == []

        # Auth
        result = await adapter.upsert_auth_server({"name": "keycloak"})
        assert result.success is False

        result = await adapter.upsert_strategy({"name": "oauth2"})
        assert result.success is False

        result = await adapter.upsert_scope({"scopeName": "read"})
        assert result.success is False

        # Aliases
        result = await adapter.upsert_alias({"name": "backend"})
        assert result.success is False

        # Config
        result = await adapter.apply_config({"jwt_issuer": "keycloak"})
        assert result.success is False

        # Archive
        data = await adapter.export_archive()
        assert data == b""


class TestStoaMappers:
    """Tests for spec mapping functions."""

    def test_map_api_spec_to_stoa(self):
        """map_api_spec_to_stoa produces correct structure."""
        result = map_api_spec_to_stoa(
            api_spec={
                "api_catalog_id": "cat-123",
                "api_name": "payments",
                "url": "https://backend.acme.com/v1",
                "spec_hash": "sha256-abc",
                "methods": ["GET", "POST"],
            },
            tenant_id="acme",
        )

        assert result["id"] == "cat-123"
        assert result["name"] == "payments"
        assert result["tenant_id"] == "acme"
        assert result["path_prefix"] == "/apis/acme/payments"
        assert result["backend_url"] == "https://backend.acme.com/v1"
        assert result["methods"] == ["GET", "POST"]
        assert result["spec_hash"] == "sha256-abc"
        assert result["activated"] is True

    def test_map_api_spec_defaults(self):
        """map_api_spec_to_stoa uses sensible defaults."""
        result = map_api_spec_to_stoa(api_spec={}, tenant_id="test")

        assert result["name"] == "unknown"
        assert result["methods"] == ["GET", "POST", "PUT", "DELETE"]
        assert result["activated"] is True

    def test_map_policy_to_stoa(self):
        """map_policy_to_stoa produces correct structure."""
        result = map_policy_to_stoa(
            {
                "id": "pol-1",
                "name": "rate-limit-100",
                "type": "rate_limit",
                "config": {"rate": 100, "window": "1m"},
                "priority": 50,
                "api_id": "api-123",
            }
        )

        assert result["id"] == "pol-1"
        assert result["name"] == "rate-limit-100"
        assert result["policy_type"] == "rate_limit"
        assert result["config"]["rate"] == 100
        assert result["priority"] == 50
        assert result["api_id"] == "api-123"


class TestStoaAdapterRegistry:
    """Tests for adapter registration in the global registry."""

    def test_registry_has_stoa(self):
        """STOA adapter is registered in AdapterRegistry."""
        from src.adapters.registry import AdapterRegistry

        assert AdapterRegistry.has_type("stoa") is True

    def test_registry_create_stoa(self):
        """AdapterRegistry.create('stoa') returns StoaGatewayAdapter instance."""
        from src.adapters.registry import AdapterRegistry

        adapter = AdapterRegistry.create("stoa", config={"base_url": "http://test:8080"})
        assert isinstance(adapter, StoaGatewayAdapter)
        assert adapter._base_url == "http://test:8080"
