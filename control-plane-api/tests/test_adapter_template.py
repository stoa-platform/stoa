"""Tests for the adapter template SDK (Step 30, Phase 5).

Verifies the template adapter skeleton, required/optional method behavior,
and AdapterRegistry registration.
"""
import pytest

from src.adapters.template import TemplateGatewayAdapter
from src.adapters.gateway_adapter_interface import AdapterResult


class TestAdapterTemplate:
    """Tests for TemplateGatewayAdapter."""

    def test_template_instantiates(self):
        """TemplateGatewayAdapter(config={...}) creates instance with config."""
        adapter = TemplateGatewayAdapter(config={
            "base_url": "http://example.com",
            "auth_config": {"type": "bearer", "token": "abc"},
        })
        assert adapter._config["base_url"] == "http://example.com"
        assert adapter._config["auth_config"]["token"] == "abc"

    @pytest.mark.asyncio
    async def test_required_methods_raise_not_implemented(self):
        """All 6 required methods raise NotImplementedError."""
        adapter = TemplateGatewayAdapter()

        with pytest.raises(NotImplementedError, match="connect"):
            await adapter.connect()

        with pytest.raises(NotImplementedError, match="disconnect"):
            await adapter.disconnect()

        with pytest.raises(NotImplementedError, match="health_check"):
            await adapter.health_check()

        with pytest.raises(NotImplementedError, match="sync_api"):
            await adapter.sync_api({"api_name": "test"}, "tenant-1")

        with pytest.raises(NotImplementedError, match="delete_api"):
            await adapter.delete_api("api-123")

        with pytest.raises(NotImplementedError, match="list_apis"):
            await adapter.list_apis()

    def test_registration_works(self):
        """AdapterRegistry.register() + create() round-trips correctly."""
        from src.adapters.registry import AdapterRegistry

        AdapterRegistry.register("test_phase5_template", TemplateGatewayAdapter)
        assert AdapterRegistry.has_type("test_phase5_template")

        instance = AdapterRegistry.create(
            "test_phase5_template",
            config={"base_url": "http://test"},
        )
        assert isinstance(instance, TemplateGatewayAdapter)
        assert instance._config["base_url"] == "http://test"
