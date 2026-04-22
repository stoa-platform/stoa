"""Deployment Orchestration Service — coordinates promotion → assignment → deploy (CAB-1888).

Sits above GatewayDeploymentService, adding:
- API resolution: accepts Git API name or catalog UUID, ensures catalog sync
- Promotion prerequisite validation (staging/prod require active promotion)
- Dev environment bypass (no promotion needed for dev)
- Auto-deploy via api_gateway_assignments
- Environment-aware gateway filtering
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.catalog import APICatalog
from ..models.gateway_instance import GatewayInstance
from ..models.promotion import Promotion, PromotionStatus
from ..repositories.api_gateway_assignment import ApiGatewayAssignmentRepository
from ..services.gateway_deployment_service import GatewayDeploymentService

logger = logging.getLogger(__name__)


class DeploymentOrchestrationService:
    """Coordinates the full deploy flow: resolve API → promotion check → deploy."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.deploy_svc = GatewayDeploymentService(db)
        self.assignment_repo = ApiGatewayAssignmentRepository(db)

    async def _resolve_api_catalog(self, tenant_id: str, api_identifier: str) -> APICatalog:
        """Resolve an API identifier to a catalog entry.

        Accepts either a UUID (catalog ID) or a string (Git API name/id).
        If the API is not in the catalog, syncs it from Git on-demand.

        Raises ValueError if the API cannot be found.
        """
        # Try as UUID first (catalog entry ID)
        try:
            catalog_uuid = UUID(api_identifier)
            result = await self.db.execute(
                select(APICatalog).where(
                    APICatalog.id == catalog_uuid,
                    APICatalog.deleted_at.is_(None),
                )
            )
            entry = result.scalar_one_or_none()
            if entry:
                return entry
        except ValueError:
            pass  # Not a UUID — treat as Git API name

        # Try by api_id (Git identifier) + tenant
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.api_id == api_identifier,
                APICatalog.tenant_id == tenant_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            return entry

        # Also try by api_name (display name used as ID in some contexts)
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.api_name == api_identifier,
                APICatalog.tenant_id == tenant_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            return entry

        # Not in catalog — sync from Git on-demand
        logger.info(
            "API '%s' not in catalog for tenant '%s', syncing from Git...",
            api_identifier,
            tenant_id,
        )
        entry = await self._sync_api_from_git(tenant_id, api_identifier)
        if entry:
            return entry

        raise ValueError(
            f"API '{api_identifier}' not found for tenant '{tenant_id}'. "
            f"Ensure the API exists in the Git repository."
        )

    async def _sync_api_from_git(self, tenant_id: str, api_id: str) -> APICatalog | None:
        """Sync a single API from Git into the catalog on-demand."""
        try:
            from ..services.git_service import git_service

            # regression for CAB-1889: use provider-agnostic is_connected, not _project
            if not git_service.is_connected():
                await git_service.connect()

            api_data = await git_service.get_api(tenant_id, api_id)
            if not api_data:
                return None

            # Upsert into catalog using the same logic as CatalogSyncService
            from ..services.catalog_sync_service import CatalogSyncService

            sync_svc = CatalogSyncService(self.db, git_service, enable_gateway_reconciliation=False)

            import contextlib

            openapi_spec = None
            with contextlib.suppress(Exception):
                openapi_spec = await git_service.get_api_openapi_spec(tenant_id, api_id)

            commit_sha: str | None = None
            with contextlib.suppress(Exception):
                # regression for CAB-1889: use provider-agnostic ABC, not _project
                commit_sha = await git_service.get_head_commit_sha(ref="main")

            await sync_svc._upsert_api(tenant_id, api_id, api_data, openapi_spec, commit_sha)
            await self.db.commit()

            # Re-fetch the entry
            result = await self.db.execute(
                select(APICatalog).where(
                    APICatalog.api_id == api_id,
                    APICatalog.tenant_id == tenant_id,
                    APICatalog.deleted_at.is_(None),
                )
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Failed to sync API '%s/%s' from Git: %s", tenant_id, api_id, e)
            return None

    async def deploy_api_to_env(
        self,
        tenant_id: str,
        api_identifier: str,
        environment: str,
        gateway_ids: list[UUID] | None = None,
        deployed_by: str = "system",
    ) -> list:
        """Deploy an API to gateways in a specific environment.

        Args:
            tenant_id: Tenant owning the API.
            api_identifier: API catalog UUID or Git API name/id.
            environment: Target environment (dev/staging/production).
            gateway_ids: Specific gateways to deploy to. If None, uses assignments.
            deployed_by: User who triggered the deployment (for audit).

        Returns:
            List of created/updated GatewayDeployment records.

        Raises:
            ValueError: If prerequisites are not met.
        """
        # 1. Resolve API to catalog entry (sync from Git if needed)
        api_catalog = await self._resolve_api_catalog(tenant_id, api_identifier)

        # 2. Validate promotion prerequisite (staging/prod only — dev is no-ceremony)
        if environment != "dev":
            has_promotion = await self._has_active_promotion(api_catalog.api_id, api_catalog.tenant_id, environment)
            if not has_promotion:
                raise ValueError(
                    f"API '{api_catalog.api_name}' has no active promotion to {environment}. "
                    f"Promote the API first before deploying to {environment}."
                )

        # 3. Resolve target gateways
        if gateway_ids is None:
            assignments = await self.assignment_repo.list_auto_deploy(api_catalog.id, environment)
            if not assignments:
                raise ValueError(
                    f"No gateway assignments with auto_deploy=True for API "
                    f"'{api_catalog.api_name}' in {environment}. "
                    f"Configure assignments or specify gateway_ids explicitly."
                )
            gateway_ids = [a.gateway_id for a in assignments]
        else:
            await self._validate_gateways_for_env(gateway_ids, environment)

        # 4. Deploy via existing GatewayDeploymentService (creates PENDING records + Kafka events)
        deployments = await self.deploy_svc.deploy_api(api_catalog.id, gateway_ids)

        # 5. Legacy mode: attempt inline sync for immediate UI feedback.
        #    SSE mode (ADR-059): Link handles sync via SSE notification.
        if settings.is_inline_sync_enabled:
            await self._try_inline_sync(deployments)

        logger.info(
            "Orchestrated deployment: api=%s env=%s gateways=%d by=%s",
            api_catalog.api_name,
            environment,
            len(deployments),
            deployed_by,
        )
        return deployments

    async def get_deployable_environments(self, tenant_id: str, api_identifier: str) -> list[dict]:
        """Get environments where this API can be deployed.

        Dev is always deployable (no promotion required).
        """
        # Resolve API — but don't fail if not in catalog
        api_id_for_promotion = api_identifier
        try:
            api_catalog = await self._resolve_api_catalog(tenant_id, api_identifier)
            api_id_for_promotion = api_catalog.api_id
            tenant_for_lookup = api_catalog.tenant_id
        except ValueError:
            tenant_for_lookup = tenant_id

        environments = []

        # Dev is always available
        environments.append(
            {
                "environment": "dev",
                "deployable": True,
                "promotion_status": "not_required",
            }
        )

        # Staging requires promotion from dev
        staging_promotion = await self._get_latest_promotion(api_id_for_promotion, tenant_for_lookup, "staging")
        environments.append(
            {
                "environment": "staging",
                "deployable": staging_promotion is not None,
                "promotion_status": staging_promotion.status if staging_promotion else "not_promoted",
            }
        )

        # Production requires promotion from staging
        prod_promotion = await self._get_latest_promotion(api_id_for_promotion, tenant_for_lookup, "production")
        environments.append(
            {
                "environment": "production",
                "deployable": prod_promotion is not None,
                "promotion_status": prod_promotion.status if prod_promotion else "not_promoted",
            }
        )

        return environments

    async def auto_deploy_on_promotion(
        self,
        api_id: str,
        tenant_id: str,
        target_environment: str,
        approved_by: str,
        promotion_id: UUID | None = None,
    ) -> list:
        """Triggered by promotion event — auto-deploy to assigned gateways."""
        # Resolve the catalog entry
        try:
            api_catalog = await self._resolve_api_catalog(tenant_id, api_id)
        except ValueError:
            logger.warning(
                "Auto-deploy skipped: cannot resolve api=%s tenant=%s",
                api_id,
                tenant_id,
            )
            return []

        # Get auto-deploy assignments
        assignments = await self.assignment_repo.list_auto_deploy(api_catalog.id, target_environment)
        if not assignments:
            logger.debug(
                "No auto-deploy assignments for api=%s env=%s",
                api_id,
                target_environment,
            )
            return []

        gateway_ids = [a.gateway_id for a in assignments]
        logger.info(
            "Auto-deploying api=%s to %d gateways in %s (triggered by promotion, approved by %s)",
            api_id,
            len(gateway_ids),
            target_environment,
            approved_by,
        )

        deployments = await self.deploy_svc.deploy_api(api_catalog.id, gateway_ids)

        # Stamp deployments with the promotion that triggered them
        if promotion_id and deployments:
            for dep in deployments:
                dep.promotion_id = promotion_id
            await self.db.flush()

        return deployments

    async def _try_inline_sync(self, deployments: list) -> None:
        """Attempt to sync deployments immediately (inline, not via Kafka/worker).

        This is best-effort — if it fails, the SyncEngine periodic loop will
        pick up PENDING records on its next cycle. The goal is to provide
        immediate feedback in the UI instead of waiting 5 minutes.
        """
        import contextlib
        from datetime import UTC, datetime

        from ..models.gateway_deployment import DeploymentSyncStatus
        from ..repositories.gateway_instance import GatewayInstanceRepository
        from ..services.credential_resolver import (
            AgentManagedGatewayError,
            create_adapter_with_credentials,
        )

        gw_repo = GatewayInstanceRepository(self.db)

        for dep in deployments:
            try:
                gateway = await gw_repo.get_by_id(dep.gateway_instance_id)
                if not gateway or gateway.status.value == "offline":
                    continue

                adapter = await create_adapter_with_credentials(
                    gateway.gateway_type.value,
                    gateway.base_url,
                    gateway.auth_config,
                    source=gateway.source,
                    gateway_name=gateway.name,
                )
                await adapter.connect()
                try:
                    now = datetime.now(UTC)
                    dep.sync_status = DeploymentSyncStatus.SYNCING
                    dep.last_sync_attempt = now
                    await self.db.flush()

                    tenant_id = (dep.desired_state or {}).get("tenant_id", "")
                    result = await adapter.sync_api(dep.desired_state, tenant_id)

                    if result.success:
                        dep.sync_status = DeploymentSyncStatus.SYNCED
                        dep.actual_state = result.data or dep.desired_state
                        dep.actual_at = now
                        dep.gateway_resource_id = result.resource_id or dep.gateway_resource_id
                        dep.last_sync_success = now
                        dep.sync_error = None
                        logger.info("Inline sync succeeded for deployment %s", dep.id)
                    else:
                        dep.sync_status = DeploymentSyncStatus.ERROR
                        dep.sync_error = result.error or "Inline sync failed"
                        dep.sync_attempts += 1
                        logger.warning("Inline sync failed for deployment %s: %s", dep.id, result.error)
                finally:
                    with contextlib.suppress(Exception):
                        await adapter.disconnect()

            except AgentManagedGatewayError:
                logger.info(
                    "Skipping inline sync for agent-managed gateway (deployment %s)",
                    dep.id,
                )
                continue
            except Exception as e:
                # Reset to PENDING so the SyncEngine periodic loop can retry
                dep.sync_status = DeploymentSyncStatus.PENDING
                dep.sync_error = str(e)[:500]
                dep.sync_attempts += 1
                logger.warning("Inline sync error for deployment %s: %s (will retry via SyncEngine)", dep.id, e)

    async def _has_active_promotion(self, api_id: str, tenant_id: str, target_environment: str) -> bool:
        result = await self.db.execute(
            select(Promotion.id)
            .where(
                Promotion.api_id == api_id,
                Promotion.tenant_id == tenant_id,
                Promotion.target_environment == target_environment,
                Promotion.status == PromotionStatus.PROMOTED.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_latest_promotion(self, api_id: str, tenant_id: str, target_environment: str) -> Promotion | None:
        result = await self.db.execute(
            select(Promotion)
            .where(
                Promotion.api_id == api_id,
                Promotion.tenant_id == tenant_id,
                Promotion.target_environment == target_environment,
                Promotion.status == PromotionStatus.PROMOTED.value,
            )
            .order_by(Promotion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _validate_gateways_for_env(self, gateway_ids: list[UUID], environment: str) -> None:
        for gw_id in gateway_ids:
            result = await self.db.execute(select(GatewayInstance).where(GatewayInstance.id == gw_id))
            gateway = result.scalar_one_or_none()
            if not gateway:
                raise ValueError(f"Gateway {gw_id} not found")
            if gateway.environment != environment:
                raise ValueError(
                    f"Gateway '{gateway.name}' is in environment '{gateway.environment}', "
                    f"not '{environment}'. Select gateways matching the target environment."
                )
