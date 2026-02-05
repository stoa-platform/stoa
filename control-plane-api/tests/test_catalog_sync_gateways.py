"""Tests for GitOps gateway deployment reconciliation in CatalogSyncService.

Step 28 (Phase 5): Verifies that the `gateways:` block in api.yaml triggers
automatic GatewayDeployment creation/update during catalog sync.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models.gateway_deployment import DeploymentSyncStatus


@pytest.mark.asyncio
class TestCatalogSyncGatewayReconciliation:
    """Tests for _reconcile_gateway_deployments() in CatalogSyncService."""

    def _make_catalog_entry(self, **overrides):
        """Create a mock APICatalog entry with sensible defaults."""
        defaults = {
            "id": uuid4(),
            "tenant_id": "acme",
            "api_id": "billing-api",
            "api_name": "Billing API",
            "version": "2.1.0",
            "openapi_spec": {"openapi": "3.0.0"},
            "api_metadata": {"name": "Billing API"},
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_gateway_instance(self, **overrides):
        """Create a mock GatewayInstance."""
        defaults = {
            "id": uuid4(),
            "name": "webmethods-prod",
            "gateway_type": MagicMock(value="webmethods"),
            "base_url": "http://wm-prod:5555",
            "auth_config": {},
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_deployment(self, **overrides):
        """Create a mock GatewayDeployment."""
        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "desired_state": {"spec_hash": "old_hash", "activated": True},
            "desired_at": datetime.now(timezone.utc),
            "sync_status": DeploymentSyncStatus.SYNCED,
            "sync_error": None,
            "sync_attempts": 0,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    async def test_parse_gateways_block_creates_deployments(self):
        """Two gateway entries in api.yaml → two PENDING deployments created."""
        from src.services.catalog_sync_service import CatalogSyncService

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git, enable_gateway_reconciliation=True)

        catalog_entry = self._make_catalog_entry()
        gw1 = self._make_gateway_instance(name="webmethods-prod")
        gw2 = self._make_gateway_instance(name="stoa-dev")

        api = {
            "name": "Billing API",
            "version": "2.1.0",
            "gateways": [
                {"instance": "webmethods-prod"},
                {"instance": "stoa-dev"},
            ],
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = catalog_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_name = AsyncMock(side_effect=lambda name: {
            "webmethods-prod": gw1,
            "stoa-dev": gw2,
        }.get(name))

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
        mock_deploy_repo.create = AsyncMock(side_effect=lambda d: d)

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ):
            await svc._reconcile_gateway_deployments("acme", "billing-api", api)

        assert mock_deploy_repo.create.await_count == 2

    async def test_resolve_instance_by_name(self):
        """Gateway instances are resolved by name via get_by_name()."""
        from src.services.catalog_sync_service import CatalogSyncService

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git)

        catalog_entry = self._make_catalog_entry()
        gw = self._make_gateway_instance(name="kong-staging")

        api = {
            "name": "API",
            "gateways": [{"instance": "kong-staging"}],
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = catalog_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_name = AsyncMock(return_value=gw)

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
        mock_deploy_repo.create = AsyncMock(side_effect=lambda d: d)

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ):
            await svc._reconcile_gateway_deployments("acme", "billing-api", api)

        mock_gw_repo.get_by_name.assert_awaited_once_with("kong-staging")

    async def test_create_deployment_pending(self):
        """New deployment is created with sync_status=PENDING."""
        from src.services.catalog_sync_service import CatalogSyncService
        from src.models.gateway_deployment import GatewayDeployment

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git)

        catalog_entry = self._make_catalog_entry()
        gw = self._make_gateway_instance()

        api = {
            "name": "API",
            "gateways": [{"instance": "webmethods-prod"}],
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = catalog_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_name = AsyncMock(return_value=gw)

        created_deployments = []
        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
        mock_deploy_repo.create = AsyncMock(side_effect=lambda d: (created_deployments.append(d), d)[1])

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ):
            await svc._reconcile_gateway_deployments("acme", "billing-api", api)

        assert len(created_deployments) == 1
        dep = created_deployments[0]
        assert dep.sync_status == DeploymentSyncStatus.PENDING
        assert dep.api_catalog_id == catalog_entry.id
        assert dep.gateway_instance_id == gw.id

    async def test_missing_instance_warning(self):
        """Unknown gateway name → warning logged, no deployment created."""
        from src.services.catalog_sync_service import CatalogSyncService

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git)

        catalog_entry = self._make_catalog_entry()

        api = {
            "name": "API",
            "gateways": [{"instance": "nonexistent-gateway"}],
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = catalog_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_name = AsyncMock(return_value=None)

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.create = AsyncMock()

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ), patch(
            "src.services.catalog_sync_service.logger"
        ) as mock_logger:
            await svc._reconcile_gateway_deployments("acme", "billing-api", api)

        mock_deploy_repo.create.assert_not_awaited()
        mock_logger.warning.assert_called_once()
        assert "nonexistent-gateway" in mock_logger.warning.call_args[0][1]

    async def test_no_gateways_block_noop(self):
        """API without gateways: block → no deployments created (backward compat)."""
        from src.services.catalog_sync_service import CatalogSyncService

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git)

        api = {"name": "Simple API", "version": "1.0.0"}

        mock_gw_repo = MagicMock()
        mock_deploy_repo = MagicMock()

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ):
            await svc._reconcile_gateway_deployments("acme", "simple-api", api)

        # No DB calls should have been made — early return
        mock_db.execute.assert_not_awaited()

    async def test_update_existing_deployment(self):
        """Existing deployment with changed state → reset to PENDING; unchanged → left alone."""
        from src.services.catalog_sync_service import CatalogSyncService

        mock_db = AsyncMock()
        mock_git = MagicMock()
        svc = CatalogSyncService(mock_db, mock_git)

        catalog_entry = self._make_catalog_entry()
        gw = self._make_gateway_instance()

        # Build the desired_state that the service would compute
        from src.services.gateway_deployment_service import GatewayDeploymentService
        expected_desired = GatewayDeploymentService.build_desired_state(catalog_entry)

        # Existing deployment with DIFFERENT desired_state (should be updated)
        existing_dep = self._make_deployment(
            api_catalog_id=catalog_entry.id,
            gateway_instance_id=gw.id,
            desired_state={"spec_hash": "totally_different"},
            sync_status=DeploymentSyncStatus.SYNCED,
        )

        api = {
            "name": "API",
            "gateways": [{"instance": "webmethods-prod"}],
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = catalog_entry
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_name = AsyncMock(return_value=gw)

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=existing_dep)
        mock_deploy_repo.update = AsyncMock(return_value=existing_dep)
        mock_deploy_repo.create = AsyncMock()

        with patch(
            "src.services.catalog_sync_service.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ), patch(
            "src.services.catalog_sync_service.GatewayDeploymentRepository",
            return_value=mock_deploy_repo,
        ):
            await svc._reconcile_gateway_deployments("acme", "billing-api", api)

        # Should update existing, not create new
        mock_deploy_repo.update.assert_awaited_once()
        mock_deploy_repo.create.assert_not_awaited()
        assert existing_dep.sync_status == DeploymentSyncStatus.PENDING
        assert existing_dep.desired_state == expected_desired
