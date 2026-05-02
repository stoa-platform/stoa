"""Tests for DeploymentOrchestrationService — deploy_api_to_env, auto_deploy, deployable_environments."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestDeploymentOrchestrationService:
    """Tests for environment-aware deployment orchestration."""

    def _make_catalog(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_name": "payments",
            "api_id": "payments-v2",
            "tenant_id": "acme",
            "version": "2.0.0",
            "openapi_spec": {"openapi": "3.0.0"},
            "api_metadata": None,
            "status": "active",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_gateway(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "kong-dev",
            "environment": "dev",
            "gateway_type": MagicMock(value="kong"),
            "base_url": "http://kong:8001",
            "auth_config": {},
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_assignment(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_id": uuid4(),
            "gateway_id": uuid4(),
            "environment": "dev",
            "auto_deploy": True,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_promotion(self, **overrides):
        from src.models.promotion import PromotionStatus

        defaults = {
            "id": uuid4(),
            "status": PromotionStatus.PROMOTED.value,
            "completed_at": MagicMock(),
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_deploy_to_dev_no_promotion_required(self):
        """Dev deployments should succeed without a promotion."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        gw = self._make_gateway()
        deployments = [MagicMock(id=uuid4())]

        db = AsyncMock()
        # Mock select(APICatalog) query
        db.execute = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(svc, "_has_active_promotion") as mock_promo,
            patch.object(svc, "_validate_gateways_for_env") as mock_validate,
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            # Mock the APICatalog query
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_deploy.return_value = deployments

            result = await svc.deploy_api_to_env(
                tenant_id="acme",
                api_identifier=str(catalog.id),
                environment="dev",
                gateway_ids=[gw.id],
                deployed_by="admin",
            )

            assert len(result) == 1
            # Promotion check should NOT be called for dev
            mock_promo.assert_not_called()
            mock_validate.assert_called_once_with([gw.id], "dev")
            mock_deploy.assert_called_once_with(catalog.id, [gw.id])

    @pytest.mark.asyncio
    async def test_deploy_to_staging_requires_promotion(self):
        """Staging deployment should fail without an active promotion."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with patch.object(svc, "_has_active_promotion", new_callable=AsyncMock) as mock_promo:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_promo.return_value = False

            with pytest.raises(ValueError, match="no active promotion"):
                await svc.deploy_api_to_env(
                    tenant_id="acme",
                    api_identifier=str(catalog.id),
                    environment="staging",
                    gateway_ids=[uuid4()],
                )

    @pytest.mark.asyncio
    async def test_deploy_to_staging_with_promotion_succeeds(self):
        """Staging deployment should succeed when promotion exists."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        deployments = [MagicMock(id=uuid4())]

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(svc, "_has_active_promotion", new_callable=AsyncMock) as mock_promo,
            patch.object(svc, "_validate_gateways_for_env", new_callable=AsyncMock),
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_promo.return_value = True
            mock_deploy.return_value = deployments

            result = await svc.deploy_api_to_env(
                tenant_id="acme",
                api_identifier=str(catalog.id),
                environment="staging",
                gateway_ids=[uuid4()],
            )
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_validate_gateways_accepts_prod_alias_for_production(self):
        """prod gateway rows satisfy production deployment requests."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        gateway = self._make_gateway(environment="prod")
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with patch.object(svc, "_get_gateway_or_raise", new_callable=AsyncMock) as mock_gateway:
            mock_gateway.return_value = gateway
            await svc._validate_gateways_for_env([gateway.id], "production")

    @pytest.mark.asyncio
    async def test_deploy_uses_assignments_when_no_gateway_ids(self):
        """When gateway_ids is None, should use auto-deploy assignments."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        gw_id = uuid4()
        assignments = [self._make_assignment(gateway_id=gw_id)]
        deployments = [MagicMock(id=uuid4())]

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign,
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_assign.return_value = assignments
            mock_deploy.return_value = deployments

            result = await svc.deploy_api_to_env(
                tenant_id="acme",
                api_identifier=str(catalog.id),
                environment="dev",
                gateway_ids=None,  # Use assignments
            )

            assert len(result) == 1
            mock_assign.assert_called_once_with(catalog.id, "dev")
            mock_deploy.assert_called_once_with(catalog.id, [gw_id])

    @pytest.mark.asyncio
    async def test_deploy_raises_when_no_assignments_and_no_gateway_ids(self):
        """Should raise when no auto-deploy assignments and no explicit gateways."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_assign.return_value = []

            with pytest.raises(ValueError, match="No gateway assignments"):
                await svc.deploy_api_to_env(
                    tenant_id="acme",
                    api_identifier=str(catalog.id),
                    environment="dev",
                    gateway_ids=None,
                )

    @pytest.mark.asyncio
    async def test_deploy_raises_for_missing_api_catalog(self):
        """Should raise when API catalog entry not found."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        api_id = str(uuid4())
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(
                svc,
                "_resolve_api_catalog",
                new_callable=AsyncMock,
                side_effect=ValueError(f"API '{api_id}' not found for tenant 'acme'."),
            ),
            pytest.raises(ValueError, match="not found for tenant"),
        ):
            await svc.deploy_api_to_env(
                tenant_id="acme",
                api_identifier=api_id,
                environment="dev",
                gateway_ids=[uuid4()],
            )

    @pytest.mark.asyncio
    async def test_auto_deploy_on_promotion_triggers_deploy(self):
        """auto_deploy_on_promotion should deploy to assigned gateways."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        gw_id = uuid4()
        assignments = [self._make_assignment(gateway_id=gw_id)]
        deployments = [MagicMock(id=uuid4())]

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign,
            patch.object(svc, "_preflight_gateway_ids", new_callable=AsyncMock) as mock_preflight,
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_assign.return_value = assignments
            mock_preflight.return_value = [MagicMock(deployable=True)]
            mock_deploy.return_value = deployments

            result = await svc.auto_deploy_on_promotion(
                api_id="payments-v2",
                tenant_id="acme",
                target_environment="dev",
                approved_by="admin",
            )

            assert len(result) == 1
            mock_preflight.assert_awaited_once_with(catalog, [gw_id])
            mock_deploy.assert_called_once_with(catalog.id, [gw_id])

    @pytest.mark.asyncio
    async def test_auto_deploy_on_promotion_uses_explicit_gateway_ids(self):
        """gateway-aware promotions bypass assignments and deploy to selected targets."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        gw_id = uuid4()
        deployments = [MagicMock(id=uuid4())]

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (
            patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign,
            patch.object(svc, "_validate_gateways_for_env", new_callable=AsyncMock) as mock_validate,
            patch.object(svc, "_preflight_gateway_ids", new_callable=AsyncMock) as mock_preflight,
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_preflight.return_value = [MagicMock(deployable=True)]
            mock_deploy.return_value = deployments

            result = await svc.auto_deploy_on_promotion(
                api_id="payments-v2",
                tenant_id="acme",
                target_environment="staging",
                approved_by="admin",
                gateway_ids=[gw_id],
            )

            assert len(result) == 1
            mock_assign.assert_not_awaited()
            mock_validate.assert_awaited_once_with([gw_id], "staging")
            mock_preflight.assert_awaited_once_with(catalog, [gw_id])
            mock_deploy.assert_called_once_with(catalog.id, [gw_id])

    @pytest.mark.asyncio
    async def test_auto_deploy_on_promotion_blocks_preflight_failure(self):
        """auto_deploy_on_promotion must not create deployments when adapter preflight fails."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        gw_id = uuid4()
        assignments = [self._make_assignment(gateway_id=gw_id)]

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        failed_preflight = MagicMock(deployable=False)
        failed_preflight.errors = [MagicMock(code="openapi_operation_responses_missing")]
        failed_preflight.gateway_name = "connect-webmethods-dev"

        with (
            patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign,
            patch.object(svc, "_preflight_gateway_ids", new_callable=AsyncMock) as mock_preflight,
            patch.object(svc.deploy_svc, "deploy_api", new_callable=AsyncMock) as mock_deploy,
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_assign.return_value = assignments
            mock_preflight.return_value = [failed_preflight]

            with pytest.raises(ValueError, match="Deployment preflight failed"):
                await svc.auto_deploy_on_promotion(
                    api_id="payments-v2",
                    tenant_id="acme",
                    target_environment="dev",
                    approved_by="admin",
                )

            mock_deploy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auto_deploy_fails_when_no_assignments(self):
        """auto_deploy_on_promotion must not silently succeed with zero runtime targets."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with patch.object(svc.assignment_repo, "list_auto_deploy", new_callable=AsyncMock) as mock_assign:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            mock_assign.return_value = []

            with pytest.raises(ValueError, match="no auto-deploy gateway assignments"):
                await svc.auto_deploy_on_promotion(
                    api_id="payments-v2",
                    tenant_id="acme",
                    target_environment="staging",
                    approved_by="admin",
                )

    @pytest.mark.asyncio
    async def test_validate_gateways_accepts_prod_production_alias(self):
        """Runtime gateway rows may store prod while public APIs pass production."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        gw_id = uuid4()
        gateway = self._make_gateway(id=gw_id, name="connect-webmethods-prod", environment="prod")
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with patch.object(svc, "_get_gateway_or_raise", new_callable=AsyncMock, return_value=gateway):
            await svc._validate_gateways_for_env([gw_id], "production")

    @pytest.mark.asyncio
    async def test_get_deployable_environments(self):
        """Should return dev as always deployable, staging/prod based on promotions."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        with (patch.object(svc, "_get_latest_promotion", new_callable=AsyncMock) as mock_promo,):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute.return_value = mock_result

            # Staging has promotion, prod does not
            mock_promo.side_effect = [
                self._make_promotion(),  # staging
                None,  # production
            ]

            result = await svc.get_deployable_environments("acme", str(catalog.id))

            assert len(result) == 3
            assert result[0]["environment"] == "dev"
            assert result[0]["deployable"] is True
            assert result[1]["environment"] == "staging"
            assert result[1]["deployable"] is True
            assert result[2]["environment"] == "production"
            assert result[2]["deployable"] is False


class TestRegressionCab1889:
    """regression for CAB-1889: _sync_api_from_git must use provider-agnostic ABC, not _project."""

    async def test_regression_cab_1889_deployment_orch_uses_get_head_commit_sha(self):
        """_sync_api_from_git must call is_connected + get_head_commit_sha, never _project."""
        from src.services.deployment_orchestration_service import (
            DeploymentOrchestrationService,
        )

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        # Stub the catalog upsert path so the test focuses on the git access pattern.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        db.execute.return_value = mock_result

        with (
            patch("src.services.git_service.git_service") as mock_git,
            patch("src.services.catalog_sync_service.CatalogSyncService") as mock_catalog_cls,
        ):
            mock_git.is_connected.return_value = True
            mock_git.connect = AsyncMock()
            mock_git.get_api = AsyncMock(return_value={"api_id": "payments", "version": "2.0.0"})
            mock_git.get_api_openapi_spec = AsyncMock(return_value={"openapi": "3.0.0"})
            mock_git.get_head_commit_sha = AsyncMock(return_value="sha123")
            mock_catalog_cls.return_value._upsert_api = AsyncMock()

            await svc._sync_api_from_git("acme", "payments")

            mock_git.is_connected.assert_called()
            # CP-1 P2 M.4: caller drops explicit ref so the provider resolves
            # it from ``settings.git.default_branch``.
            mock_git.get_head_commit_sha.assert_awaited_once_with()
            # _project must never be touched — if it is, this attribute access would work on MagicMock
            # so we assert that only the interface methods were called.
            assert not any(
                "_project" in str(call) for call in mock_git.mock_calls
            ), f"_project leaked into calls: {mock_git.mock_calls}"
