"""Tests for GatewayInstanceService — gateway CRUD + health check."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestGatewayInstanceService:
    """Tests for gateway instance business logic."""

    def _make_gateway(self, **overrides):
        """Create a mock GatewayInstance."""
        defaults = {
            "id": uuid4(),
            "name": "webmethods-prod",
            "display_name": "webMethods Production",
            "gateway_type": MagicMock(value="webmethods"),
            "environment": "production",
            "tenant_id": None,
            "base_url": "https://gateway.example.com",
            "auth_config": {},
            "status": MagicMock(value="offline"),
            "capabilities": ["rest", "oidc"],
            "tags": [],
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_create_success(self):
        """Successful gateway registration."""
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.AdapterRegistry") as mock_registry, \
             patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:

            mock_registry.has_type.return_value = True
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(side_effect=lambda inst: inst)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            data = MagicMock()
            data.name = "kong-staging"
            data.display_name = "Kong Staging"
            data.gateway_type = "webmethods"
            data.environment = "staging"
            data.tenant_id = None
            data.base_url = "https://kong.example.com"
            data.auth_config = {}
            data.capabilities = []
            data.tags = []

            result = await svc.create(data)
            mock_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_unknown_type_raises(self):
        """Creating a gateway with unknown type raises ValueError."""
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.AdapterRegistry") as mock_registry:
            mock_registry.has_type.return_value = False
            mock_registry.list_types.return_value = ["webmethods"]

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)

            data = MagicMock()
            data.gateway_type = "unknown_gw"

            with pytest.raises(ValueError, match="No adapter registered"):
                await svc.create(data)

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(self):
        """Creating a gateway with duplicate name raises ValueError."""
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.AdapterRegistry") as mock_registry, \
             patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:

            mock_registry.has_type.return_value = True
            mock_repo = MockRepo.return_value
            mock_repo.get_by_name = AsyncMock(return_value=self._make_gateway())

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            data = MagicMock()
            data.name = "webmethods-prod"
            data.gateway_type = "webmethods"

            with pytest.raises(ValueError, match="already exists"):
                await svc.create(data)

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        """Get gateway by ID returns the instance."""
        db = AsyncMock()
        gw = self._make_gateway()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            result = await svc.get_by_id(gw.id)
            assert result == gw

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        """Deleting a non-existent gateway raises ValueError."""
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            with pytest.raises(ValueError, match="not found"):
                await svc.delete(uuid4())

    @pytest.mark.asyncio
    async def test_update_applies_fields(self):
        """Update applies only provided fields."""
        db = AsyncMock()
        gw = self._make_gateway()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            data = MagicMock()
            data.display_name = "Updated Name"
            data.base_url = None
            data.auth_config = None
            data.capabilities = None
            data.tags = None
            data.environment = None

            await svc.update(gw.id, data)
            assert gw.display_name == "Updated Name"
            mock_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check returns online status on success."""
        db = AsyncMock()
        gw = self._make_gateway()

        from src.adapters.gateway_adapter_interface import AdapterResult

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.health_check = AsyncMock(
            return_value=AdapterResult(success=True, data={"version": "10.15"})
        )

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo, \
             patch("src.services.gateway_instance_service.AdapterRegistry") as MockRegistry:

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update_status = AsyncMock()

            MockRegistry.create.return_value = mock_adapter

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            result = await svc.health_check(gw.id)
            assert result["status"] == "online"
            mock_adapter.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Health check returns offline status on exception."""
        db = AsyncMock()
        gw = self._make_gateway()

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock(side_effect=ConnectionError("refused"))
        mock_adapter.disconnect = AsyncMock()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo, \
             patch("src.services.gateway_instance_service.AdapterRegistry") as MockRegistry:

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update_status = AsyncMock()

            MockRegistry.create.return_value = mock_adapter

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            result = await svc.health_check(gw.id)
            assert result["status"] == "offline"
            assert "refused" in result["details"]["error"]


# ── Additional coverage: list, update edge cases, health_check not found (CAB-1538) ──


class TestGatewayInstanceServiceAdditional:
    """Additional tests for uncovered branches."""

    def _make_gateway(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "kong-prod",
            "display_name": "Kong Production",
            "gateway_type": MagicMock(value="kong"),
            "environment": "production",
            "base_url": "https://kong.example.com",
            "auth_config": {},
            "capabilities": [],
            "tags": [],
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_list_with_gateway_type_converts_to_enum(self):
        db = AsyncMock()
        gw = self._make_gateway()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo, \
             patch("src.services.gateway_instance_service.GatewayType") as MockGwType:

            MockGwType.return_value = "kong_enum"
            mock_repo = MockRepo.return_value
            mock_repo.list_all = AsyncMock(return_value=([gw], 1))

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            _result, total = await svc.list(gateway_type="kong", environment="prod")

            MockGwType.assert_called_once_with("kong")
            mock_repo.list_all.assert_awaited_once_with(
                gateway_type="kong_enum", environment="prod", tenant_id=None, page=1, page_size=50
            )
            assert total == 1

    @pytest.mark.asyncio
    async def test_list_without_gateway_type_passes_none(self):
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo, \
             patch("src.services.gateway_instance_service.GatewayType") as MockGwType:

            mock_repo = MockRepo.return_value
            mock_repo.list_all = AsyncMock(return_value=([], 0))

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            await svc.list()

            MockGwType.assert_not_called()
            mock_repo.list_all.assert_awaited_once_with(
                gateway_type=None, environment=None, tenant_id=None, page=1, page_size=50
            )

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            with pytest.raises(ValueError, match="not found"):
                await svc.update(uuid4(), MagicMock())

    @pytest.mark.asyncio
    async def test_update_all_fields(self):
        db = AsyncMock()
        gw = self._make_gateway()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            data = MagicMock()
            data.display_name = "New Name"
            data.base_url = "https://new.example.com"
            data.auth_config = {"token": "abc"}
            data.capabilities = ["rest"]
            data.tags = ["prod"]
            data.environment = "staging"

            await svc.update(gw.id, data)

            assert gw.display_name == "New Name"
            assert gw.base_url == "https://new.example.com"
            assert gw.auth_config == {"token": "abc"}
            assert gw.capabilities == ["rest"]
            assert gw.tags == ["prod"]
            assert gw.environment == "staging"
            mock_repo.update.assert_awaited_once_with(gw)

    @pytest.mark.asyncio
    async def test_update_skips_none_fields(self):
        db = AsyncMock()
        gw = self._make_gateway()
        original_url = gw.base_url

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=gw)
            mock_repo.update = AsyncMock(return_value=gw)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            data = MagicMock()
            data.display_name = None
            data.base_url = None
            data.auth_config = None
            data.capabilities = None
            data.tags = None
            data.environment = None

            await svc.update(gw.id, data)
            assert gw.base_url == original_url

    @pytest.mark.asyncio
    async def test_health_check_not_found_raises(self):
        db = AsyncMock()

        with patch("src.services.gateway_instance_service.GatewayInstanceRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            from src.services.gateway_instance_service import GatewayInstanceService

            svc = GatewayInstanceService(db)
            svc.repo = mock_repo

            with pytest.raises(ValueError, match="not found"):
                await svc.health_check(uuid4())
