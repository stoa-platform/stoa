"""Deployment Orchestration Service — coordinates promotion → assignment → deploy (CAB-1888).

Sits above GatewayDeploymentService, adding:
- Promotion prerequisite validation (staging/prod require active promotion)
- Dev environment bypass (no promotion needed for dev)
- Auto-deploy via api_gateway_assignments
- Environment-aware gateway filtering
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.catalog import APICatalog
from ..models.gateway_instance import GatewayInstance
from ..models.promotion import Promotion, PromotionStatus
from ..repositories.api_gateway_assignment import ApiGatewayAssignmentRepository
from ..services.gateway_deployment_service import GatewayDeploymentService

logger = logging.getLogger(__name__)


class DeploymentOrchestrationService:
    """Coordinates the full deploy flow: promotion check → assignment lookup → deploy."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.deploy_svc = GatewayDeploymentService(db)
        self.assignment_repo = ApiGatewayAssignmentRepository(db)

    async def deploy_api_to_env(
        self,
        api_catalog_id: UUID,
        environment: str,
        gateway_ids: list[UUID] | None = None,
        deployed_by: str = "system",
    ) -> list:
        """Deploy an API to gateways in a specific environment.

        Args:
            api_catalog_id: API catalog entry ID.
            environment: Target environment (dev/staging/production).
            gateway_ids: Specific gateways to deploy to. If None, uses assignments.
            deployed_by: User who triggered the deployment (for audit).

        Returns:
            List of created/updated GatewayDeployment records.

        Raises:
            ValueError: If prerequisites are not met.
        """
        # 1. Validate API catalog entry exists
        result = await self.db.execute(
            select(APICatalog).where(APICatalog.id == api_catalog_id)
        )
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            raise ValueError("API catalog entry not found")

        # 2. Validate promotion prerequisite (staging/prod only — dev is no-ceremony)
        if environment != "dev":
            has_promotion = await self._has_active_promotion(
                api_catalog.api_id, api_catalog.tenant_id, environment
            )
            if not has_promotion:
                raise ValueError(
                    f"API '{api_catalog.api_name}' has no active promotion to {environment}. "
                    f"Promote the API first before deploying to {environment}."
                )

        # 3. Resolve target gateways
        if gateway_ids is None:
            # Use default assignments for this API/env
            assignments = await self.assignment_repo.list_auto_deploy(api_catalog_id, environment)
            if not assignments:
                raise ValueError(
                    f"No gateway assignments with auto_deploy=True for API "
                    f"'{api_catalog.api_name}' in {environment}. "
                    f"Configure assignments or specify gateway_ids explicitly."
                )
            gateway_ids = [a.gateway_id for a in assignments]
        else:
            # Validate specified gateways belong to the target environment
            await self._validate_gateways_for_env(gateway_ids, environment)

        # 4. Deploy via existing GatewayDeploymentService
        deployments = await self.deploy_svc.deploy_api(api_catalog_id, gateway_ids)

        logger.info(
            "Orchestrated deployment: api=%s env=%s gateways=%d by=%s",
            api_catalog.api_name,
            environment,
            len(deployments),
            deployed_by,
        )
        return deployments

    async def get_deployable_environments(self, api_catalog_id: UUID) -> list[dict]:
        """Get environments where this API can be deployed.

        Returns a list of environments with their promotion status.
        Dev is always deployable (no promotion required).
        """
        result = await self.db.execute(
            select(APICatalog).where(APICatalog.id == api_catalog_id)
        )
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            return []

        environments = []

        # Dev is always available (no-ceremony)
        environments.append({
            "environment": "dev",
            "deployable": True,
            "promotion_status": "not_required",
        })

        # Staging requires promotion from dev
        staging_promotion = await self._get_latest_promotion(
            api_catalog.api_id, api_catalog.tenant_id, "staging"
        )
        environments.append({
            "environment": "staging",
            "deployable": staging_promotion is not None,
            "promotion_status": staging_promotion.status if staging_promotion else "not_promoted",
        })

        # Production requires promotion from staging
        prod_promotion = await self._get_latest_promotion(
            api_catalog.api_id, api_catalog.tenant_id, "production"
        )
        environments.append({
            "environment": "production",
            "deployable": prod_promotion is not None,
            "promotion_status": prod_promotion.status if prod_promotion else "not_promoted",
        })

        return environments

    async def auto_deploy_on_promotion(
        self,
        api_id: str,
        tenant_id: str,
        target_environment: str,
        approved_by: str,
    ) -> list:
        """Triggered by promotion event — auto-deploy to assigned gateways.

        Only fires for environments where auto_deploy assignments exist.

        Returns:
            List of created GatewayDeployment records (empty if no auto-deploy assignments).
        """
        # Find the API catalog entry
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.api_id == api_id,
                APICatalog.tenant_id == tenant_id,
            )
        )
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            logger.warning(
                "Auto-deploy skipped: no catalog entry for api=%s tenant=%s",
                api_id, tenant_id,
            )
            return []

        # Get auto-deploy assignments for this environment
        assignments = await self.assignment_repo.list_auto_deploy(
            api_catalog.id, target_environment
        )
        if not assignments:
            logger.debug(
                "No auto-deploy assignments for api=%s env=%s",
                api_id, target_environment,
            )
            return []

        gateway_ids = [a.gateway_id for a in assignments]
        logger.info(
            "Auto-deploying api=%s to %d gateways in %s (triggered by promotion, approved by %s)",
            api_id, len(gateway_ids), target_environment, approved_by,
        )

        return await self.deploy_svc.deploy_api(api_catalog.id, gateway_ids)

    async def _has_active_promotion(
        self, api_id: str, tenant_id: str, target_environment: str
    ) -> bool:
        """Check if a promoted promotion exists for this API/env."""
        result = await self.db.execute(
            select(Promotion.id).where(
                Promotion.api_id == api_id,
                Promotion.tenant_id == tenant_id,
                Promotion.target_environment == target_environment,
                Promotion.status == PromotionStatus.PROMOTED.value,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_latest_promotion(
        self, api_id: str, tenant_id: str, target_environment: str
    ) -> Promotion | None:
        """Get the latest completed promotion to an environment."""
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

    async def _validate_gateways_for_env(
        self, gateway_ids: list[UUID], environment: str
    ) -> None:
        """Validate that specified gateways belong to the target environment."""
        for gw_id in gateway_ids:
            result = await self.db.execute(
                select(GatewayInstance).where(GatewayInstance.id == gw_id)
            )
            gateway = result.scalar_one_or_none()
            if not gateway:
                raise ValueError(f"Gateway {gw_id} not found")
            if gateway.environment != environment:
                raise ValueError(
                    f"Gateway '{gateway.name}' is in environment '{gateway.environment}', "
                    f"not '{environment}'. Select gateways matching the target environment."
                )
