"""Tests for GatewayImportService — reverse sync from gateway to catalog.

Step 29 (Phase 5): Verifies import and preview functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.gateway_deployment import DeploymentSyncStatus


@pytest.mark.asyncio
class TestGatewayImportService:
    """Tests for GatewayImportService."""

    def _make_gateway(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "stoa-prod",
            "gateway_type": MagicMock(value="stoa"),
            "base_url": "http://gateway:8080",
            "auth_config": {"admin_token": "secret"},
            "tenant_id": "acme",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    async def test_import_new_apis(self):
        """Two new APIs from gateway → 2 APICatalog entries + 2 SYNCED deployments."""
        from src.services.gateway_import_service import GatewayImportService

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        gateway = self._make_gateway()

        # Adapter returns 2 APIs
        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.list_apis = AsyncMock(return_value=[
            {"id": "api-1", "name": "Payments API", "tenant_id": "acme", "version": "1.0"},
            {"id": "api-2", "name": "Users API", "tenant_id": "acme", "version": "2.0"},
        ])

        # No existing catalog entries
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.create = AsyncMock(side_effect=lambda d: d)

        with patch(
            "src.services.gateway_import_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.gateway_import_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.gateway_import_service.AdapterRegistry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_adapter

            svc = GatewayImportService(mock_db)
            result = await svc.import_from_gateway(gateway.id)

        assert result.created == 2
        assert result.skipped == 0
        assert len(result.errors) == 0
        assert mock_deploy_repo.create.await_count == 2
        # Verify adapter was connected and disconnected
        mock_adapter.connect.assert_awaited_once()
        mock_adapter.disconnect.assert_awaited_once()

    async def test_skip_existing_apis(self):
        """API already in catalog → skipped, result.skipped=1."""
        from src.services.gateway_import_service import GatewayImportService

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        gateway = self._make_gateway()

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.list_apis = AsyncMock(return_value=[
            {"id": "existing-api", "name": "Existing API", "tenant_id": "acme"},
        ])

        # Existing catalog entry found
        existing_entry = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = existing_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.create = AsyncMock()

        with patch(
            "src.services.gateway_import_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.gateway_import_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.gateway_import_service.AdapterRegistry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_adapter

            svc = GatewayImportService(mock_db)
            result = await svc.import_from_gateway(gateway.id)

        assert result.created == 0
        assert result.skipped == 1
        mock_deploy_repo.create.assert_not_awaited()

    async def test_preview_mode(self):
        """preview_import() returns list without creating any records."""
        from src.services.gateway_import_service import GatewayImportService

        mock_db = AsyncMock()
        gateway = self._make_gateway()

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.list_apis = AsyncMock(return_value=[
            {"id": "new-api", "name": "New API", "tenant_id": "acme"},
            {"id": "existing-api", "name": "Existing", "tenant_id": "acme"},
        ])

        # First call returns None (new), second returns existing
        mock_execute_result_new = MagicMock()
        mock_execute_result_new.scalar_one_or_none.return_value = None
        mock_execute_result_existing = MagicMock()
        mock_execute_result_existing.scalar_one_or_none.return_value = MagicMock()
        mock_db.execute = AsyncMock(
            side_effect=[mock_execute_result_new, mock_execute_result_existing]
        )

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_deploy_repo = MagicMock()

        with patch(
            "src.services.gateway_import_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.gateway_import_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.gateway_import_service.AdapterRegistry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_adapter

            svc = GatewayImportService(mock_db)
            previews = await svc.preview_import(gateway.id)

        assert len(previews) == 2
        assert previews[0].action == "create"
        assert previews[1].action == "skip"
        # No writes should have occurred
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()
        mock_db.commit.assert_not_called()

    async def test_empty_gateway(self):
        """Gateway has no APIs → ImportResult(created=0, skipped=0)."""
        from src.services.gateway_import_service import GatewayImportService

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        gateway = self._make_gateway()

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.list_apis = AsyncMock(return_value=[])

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_deploy_repo = MagicMock()

        with patch(
            "src.services.gateway_import_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.gateway_import_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.gateway_import_service.AdapterRegistry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_adapter

            svc = GatewayImportService(mock_db)
            result = await svc.import_from_gateway(gateway.id)

        assert result.created == 0
        assert result.skipped == 0
        assert len(result.errors) == 0

    async def test_adapter_error_handling(self):
        """Adapter list_apis() failure → ValueError propagated."""
        from src.services.gateway_import_service import GatewayImportService

        mock_db = AsyncMock()
        gateway = self._make_gateway()

        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.list_apis = AsyncMock(side_effect=Exception("Connection refused"))

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_deploy_repo = MagicMock()

        with patch(
            "src.services.gateway_import_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.gateway_import_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.gateway_import_service.AdapterRegistry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_adapter

            svc = GatewayImportService(mock_db)
            with pytest.raises(Exception, match="Connection refused"):
                await svc.import_from_gateway(gateway.id)

        # Adapter disconnect should still be called (finally block)
        mock_adapter.disconnect.assert_awaited_once()
