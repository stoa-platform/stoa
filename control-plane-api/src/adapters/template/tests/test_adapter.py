"""Test skeleton for your adapter — copy and fill in.

This file demonstrates the testing pattern for STOA gateway adapters.
Copy it alongside your adapter implementation and replace the mock
responses with your gateway's actual API responses.
"""

import pytest

from src.adapters.template import TemplateGatewayAdapter


class TestTemplateAdapterSkeleton:
    """Verify the template adapter skeleton works correctly."""

    def test_instantiates_with_config(self):
        """Adapter can be created with a config dict."""
        adapter = TemplateGatewayAdapter(config={
            "base_url": "http://my-gateway:8080",
            "auth_config": {"token": "secret"},
        })
        assert adapter._config["base_url"] == "http://my-gateway:8080"

    @pytest.mark.asyncio
    async def test_required_methods_raise_not_implemented(self):
        """All 6 required methods raise NotImplementedError."""
        adapter = TemplateGatewayAdapter()

        with pytest.raises(NotImplementedError):
            await adapter.connect()

        with pytest.raises(NotImplementedError):
            await adapter.disconnect()

        with pytest.raises(NotImplementedError):
            await adapter.health_check()

        with pytest.raises(NotImplementedError):
            await adapter.sync_api({"api_name": "test"}, "tenant-1")

        with pytest.raises(NotImplementedError):
            await adapter.delete_api("api-123")

        with pytest.raises(NotImplementedError):
            await adapter.list_apis()

    @pytest.mark.asyncio
    async def test_optional_methods_return_not_supported(self):
        """Optional methods return AdapterResult(success=False)."""
        adapter = TemplateGatewayAdapter()

        result = await adapter.upsert_policy({"name": "cors"})
        assert result.success is False
        assert "Not supported" in result.error

        result = await adapter.delete_policy("policy-1")
        assert result.success is False

        policies = await adapter.list_policies()
        assert policies == []

        result = await adapter.provision_application({"name": "app"})
        assert result.success is False

        result = await adapter.deprovision_application("app-1")
        assert result.success is False

        apps = await adapter.list_applications()
        assert apps == []

        result = await adapter.upsert_auth_server({})
        assert result.success is False

        result = await adapter.upsert_strategy({})
        assert result.success is False

        result = await adapter.upsert_scope({})
        assert result.success is False

        result = await adapter.upsert_alias({})
        assert result.success is False

        result = await adapter.apply_config({})
        assert result.success is False

        archive = await adapter.export_archive()
        assert archive == b""

    def test_registry_registration(self):
        """Template adapter can be registered and created via AdapterRegistry."""
        from src.adapters.registry import AdapterRegistry

        AdapterRegistry.register("test_template", TemplateGatewayAdapter)
        assert AdapterRegistry.has_type("test_template")

        instance = AdapterRegistry.create(
            "test_template",
            config={"base_url": "http://test:8080"},
        )
        assert isinstance(instance, TemplateGatewayAdapter)
        assert instance._config["base_url"] == "http://test:8080"
