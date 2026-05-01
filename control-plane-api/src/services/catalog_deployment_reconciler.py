"""Reconcile catalog deployment targets into ``GatewayDeployment`` rows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance
from src.repositories.api_gateway_assignment import ApiGatewayAssignmentRepository
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.services.catalog_api_definition import (
    CatalogDeploymentTarget,
    environment_matches,
    extract_deployment_targets,
    extract_target_gateway_names,
    normalize_api_definition,
)
from src.services.gateway_deployment_service import GatewayDeploymentService

logger = logging.getLogger(__name__)


class CatalogDeploymentReconciler:
    """Materialize Git catalog runtime targets into GatewayDeployment rows."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.gw_repo = GatewayInstanceRepository(db)
        self.deploy_repo = GatewayDeploymentRepository(db)
        self.assignment_repo = ApiGatewayAssignmentRepository(db)

    async def reconcile_api(
        self,
        *,
        tenant_id: str,
        api_id: str,
        api_content: dict[str, Any],
        catalog_entry: APICatalog | None = None,
    ) -> bool:
        """Reconcile one API's catalog targets.

        Returns True when the DB session was mutated.  The caller owns commit /
        rollback so this can run inside the same transaction as api_catalog
        projection.
        """
        api = normalize_api_definition(api_content)
        targets = extract_deployment_targets(api)
        desired_target_names = extract_target_gateway_names(api)
        if not targets and not desired_target_names:
            return False

        catalog_entry = catalog_entry or await self._get_catalog_entry(tenant_id, api_id)
        if catalog_entry is None:
            return False

        changed = False
        if list(catalog_entry.target_gateways or []) != desired_target_names:
            catalog_entry.target_gateways = desired_target_names
            changed = True

        if not targets:
            return changed

        base_desired_state = GatewayDeploymentService.build_desired_state(catalog_entry)
        for target in targets:
            if not target.instance:
                assigned_gateways = await self._resolve_assignment_gateways(catalog_entry, target)
                if assigned_gateways:
                    for gateway in assigned_gateways:
                        desired_state = {
                            **base_desired_state,
                            "activated": target.activated,
                            "target_gateway_name": gateway.name,
                            "target_environment": gateway.environment,
                            "target_source": "assignment",
                        }
                        changed = await self._upsert_deployment(catalog_entry, gateway, desired_state) or changed
                    continue

                logger.warning(
                    "GitOps: deployment environment '%s' for API %s/%s has no gateway target; "
                    "add gateways: or deployments.<env>.gateways to make DR materializable",
                    target.environment,
                    tenant_id,
                    api_id,
                )
                continue

            gateway = await self._resolve_gateway(target)
            if not gateway:
                logger.warning(
                    "GitOps: gateway instance '%s' not found for API %s/%s — skipping",
                    target.instance,
                    tenant_id,
                    api_id,
                )
                continue
            if not environment_matches(getattr(gateway, "environment", None), target.environment):
                logger.warning(
                    "GitOps: gateway instance '%s' environment '%s' does not match target '%s' for API %s/%s",
                    target.instance,
                    getattr(gateway, "environment", None),
                    target.environment,
                    tenant_id,
                    api_id,
                )
                continue

            desired_state = {
                **base_desired_state,
                "activated": target.activated,
                "target_gateway_name": target.instance,
                "target_environment": target.environment,
                "target_source": target.source,
            }
            changed = await self._upsert_deployment(catalog_entry, gateway, desired_state) or changed

        if changed:
            await self.db.flush()
        return changed

    async def _get_catalog_entry(self, tenant_id: str, api_id: str) -> APICatalog | None:
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.tenant_id == tenant_id,
                APICatalog.api_id == api_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_gateway(self, target: CatalogDeploymentTarget) -> GatewayInstance | None:
        assert target.instance is not None
        gateway = await self.gw_repo.get_by_name(target.instance)
        if gateway:
            return gateway
        return await self.gw_repo.get_self_registered_by_hostname(target.instance)

    async def _resolve_assignment_gateways(
        self,
        catalog_entry: APICatalog,
        target: CatalogDeploymentTarget,
    ) -> list[GatewayInstance]:
        if not target.environment:
            return []

        assignments = await self.assignment_repo.list_auto_deploy(catalog_entry.id, target.environment)
        gateways: list[GatewayInstance] = []
        for assignment in assignments:
            gateway = await self.gw_repo.get_by_id(assignment.gateway_id)
            if not gateway:
                logger.warning(
                    "GitOps: assignment gateway '%s' not found for API %s/%s — skipping",
                    assignment.gateway_id,
                    catalog_entry.tenant_id,
                    catalog_entry.api_id,
                )
                continue
            if not environment_matches(gateway.environment, target.environment):
                logger.warning(
                    "GitOps: assignment gateway '%s' environment '%s' does not match target '%s' for API %s/%s",
                    gateway.name,
                    gateway.environment,
                    target.environment,
                    catalog_entry.tenant_id,
                    catalog_entry.api_id,
                )
                continue
            gateways.append(gateway)
        return gateways

    async def _upsert_deployment(
        self,
        catalog_entry: APICatalog,
        gateway: GatewayInstance,
        desired_state: dict[str, Any],
    ) -> bool:
        existing = await self.deploy_repo.get_by_api_and_gateway(catalog_entry.id, gateway.id)
        now = datetime.now(UTC)
        if existing:
            if existing.desired_state == desired_state:
                return False
            existing.desired_state = desired_state
            existing.desired_at = now
            existing.sync_status = DeploymentSyncStatus.PENDING
            existing.sync_error = None
            existing.sync_attempts = 0
            existing.desired_generation = (existing.desired_generation or 0) + 1
            await self.deploy_repo.update(existing)
            logger.info(
                "GitOps: updated deployment for %s/%s -> %s",
                catalog_entry.tenant_id,
                catalog_entry.api_id,
                getattr(gateway, "name", gateway.id),
            )
            return True

        deployment = GatewayDeployment(
            api_catalog_id=catalog_entry.id,
            gateway_instance_id=gateway.id,
            desired_state=desired_state,
            desired_at=now,
            sync_status=DeploymentSyncStatus.PENDING,
        )
        await self.deploy_repo.create(deployment)
        logger.info(
            "GitOps: created deployment for %s/%s -> %s",
            catalog_entry.tenant_id,
            catalog_entry.api_id,
            getattr(gateway, "name", gateway.id),
        )
        return True
