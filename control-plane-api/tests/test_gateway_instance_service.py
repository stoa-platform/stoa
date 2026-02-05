"""Tests for GatewayInstanceService — gateway CRUD + health check."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


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
