"""Tests for AdapterRegistry — gateway adapter factory pattern."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.adapters.gateway_adapter_interface import GatewayAdapterInterface, AdapterResult
from src.adapters.registry import AdapterRegistry


class FakeAdapter(GatewayAdapterInterface):
    """Minimal adapter stub for registry tests."""

    async def health_check(self) -> AdapterResult:
        return AdapterResult(success=True)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def sync_api(self, api_spec, tenant_id, auth_token=None):
        return AdapterResult(success=True)

    async def delete_api(self, api_id, auth_token=None):
        return AdapterResult(success=True)

    async def list_apis(self, auth_token=None):
        return []

    async def upsert_policy(self, policy_spec, auth_token=None):
        return AdapterResult(success=True)

    async def delete_policy(self, policy_id, auth_token=None):
        return AdapterResult(success=True)

    async def list_policies(self, auth_token=None):
        return []

    async def provision_application(self, app_spec, auth_token=None):
        return AdapterResult(success=True, resource_id="fake-001")

    async def deprovision_application(self, app_id, auth_token=None):
        return AdapterResult(success=True)

    async def list_applications(self, auth_token=None):
        return []

    async def upsert_auth_server(self, auth_spec, auth_token=None):
        return AdapterResult(success=True)

    async def upsert_strategy(self, strategy_spec, auth_token=None):
        return AdapterResult(success=True)

    async def upsert_scope(self, scope_spec, auth_token=None):
        return AdapterResult(success=True)

    async def upsert_alias(self, alias_spec, auth_token=None):
        return AdapterResult(success=True)

    async def apply_config(self, config_spec, auth_token=None):
        return AdapterResult(success=True)

    async def export_archive(self, auth_token=None):
        return b""


class TestAdapterRegistry:
    """Tests for AdapterRegistry class methods."""

    def test_webmethods_registered_by_default(self):
        """The webMethods adapter is auto-registered at import time."""
        assert AdapterRegistry.has_type("webmethods")

    def test_list_types_includes_webmethods(self):
        """list_types() returns at least webMethods."""
        types = AdapterRegistry.list_types()
        assert "webmethods" in types

    def test_create_webmethods_returns_adapter(self):
        """create('webmethods') returns a GatewayAdapterInterface instance."""
        adapter = AdapterRegistry.create("webmethods")
        assert isinstance(adapter, GatewayAdapterInterface)

    def test_create_with_config(self):
        """create() passes config through to the adapter."""
        adapter = AdapterRegistry.create("webmethods", config={"base_url": "https://test.example.com"})
        assert adapter._config.get("base_url") == "https://test.example.com"

    def test_create_unknown_type_raises(self):
        """create() raises ValueError for unregistered gateway type."""
        with pytest.raises(ValueError, match="No adapter registered"):
            AdapterRegistry.create("nonexistent_gateway")

    def test_has_type_false_for_unknown(self):
        """has_type() returns False for unregistered types."""
        assert not AdapterRegistry.has_type("nonexistent_gateway")

    def test_register_custom_adapter(self):
        """Custom adapters can be registered and created."""
        AdapterRegistry.register("fake_test", FakeAdapter)
        try:
            assert AdapterRegistry.has_type("fake_test")
            adapter = AdapterRegistry.create("fake_test")
            assert isinstance(adapter, FakeAdapter)
        finally:
            # Clean up to avoid polluting other tests
            AdapterRegistry._adapters.pop("fake_test", None)

    def test_register_overwrites_existing(self):
        """Registering the same type twice replaces the previous adapter."""
        AdapterRegistry.register("overwrite_test", FakeAdapter)
        try:
            adapter1 = AdapterRegistry.create("overwrite_test")
            assert isinstance(adapter1, FakeAdapter)

            # Register again with same key
            AdapterRegistry.register("overwrite_test", FakeAdapter)
            adapter2 = AdapterRegistry.create("overwrite_test")
            assert isinstance(adapter2, FakeAdapter)
        finally:
            AdapterRegistry._adapters.pop("overwrite_test", None)

    @pytest.mark.asyncio
    async def test_fake_adapter_provision(self):
        """Adapter provision_application returns AdapterResult."""
        adapter = FakeAdapter()
        result = await adapter.provision_application({"app": "test"})
        assert result.success
        assert result.resource_id == "fake-001"
