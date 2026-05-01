"""Deployment Orchestration Service — coordinates promotion → assignment → deploy (CAB-1888).

Sits above GatewayDeploymentService, adding:
- API resolution: accepts Git API name or catalog UUID, ensures catalog sync
- Promotion prerequisite validation (staging/prod require active promotion)
- Dev environment bypass (no promotion needed for dev)
- Auto-deploy via api_gateway_assignments
- Environment-aware gateway filtering
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.catalog import APICatalog
from ..models.gateway_instance import GatewayInstance
from ..models.promotion import Promotion, PromotionStatus
from ..repositories.api_gateway_assignment import ApiGatewayAssignmentRepository
from ..services.environment_aliases import (
    deployment_environment_aliases,
    deployment_environment_matches,
    normalize_deployment_environment,
)
from ..services.gateway_deployment_service import GatewayDeploymentService
from ..services.gateway_topology import normalize_gateway_topology

logger = logging.getLogger(__name__)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


@dataclass(frozen=True)
class DeploymentPreflightError:
    """A deterministic deployment preflight error for one gateway target."""

    gateway_id: str
    gateway_name: str
    target_gateway_type: str
    code: str
    message: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return {
            "gateway_id": self.gateway_id,
            "gateway_name": self.gateway_name,
            "target_gateway_type": self.target_gateway_type,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass(frozen=True)
class DeploymentPreflightResult:
    """Preflight result for one gateway target."""

    gateway_id: str
    gateway_name: str
    target_gateway_type: str
    deployable: bool
    errors: list[DeploymentPreflightError]

    def as_dict(self) -> dict:
        return {
            "gateway_id": self.gateway_id,
            "gateway_name": self.gateway_name,
            "target_gateway_type": self.target_gateway_type,
            "deployable": self.deployable,
            "errors": [error.as_dict() for error in self.errors],
        }


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

            # CP-1 H.2: catch only FileNotFoundError (missing spec / missing
            # head commit are expected "None" outcomes). Any transient
            # provider failure (TimeoutError, rate-limit, auth error, etc.)
            # propagates to the outer except, which short-circuits the
            # upsert — better to refuse syncing than to persist a corrupt
            # catalog row with silently-None fields. Stays provider-agnostic
            # on purpose: do NOT import PyGithub / python-gitlab exceptions
            # in this layer (CAB-1889 GitProvider abstraction invariant).
            openapi_spec = None
            try:
                openapi_spec = await git_service.get_api_openapi_spec(tenant_id, api_id)
            except FileNotFoundError:
                logger.debug("No OpenAPI spec for API '%s/%s' — syncing without spec", tenant_id, api_id)

            commit_sha: str | None = None
            try:
                # regression for CAB-1889: use provider-agnostic ABC, not _project
                # CP-1 P2 (M.4): drop explicit ref so it resolves to
                # settings.git.default_branch.
                commit_sha = await git_service.get_head_commit_sha()
            except FileNotFoundError:
                logger.debug("No head commit available for API '%s/%s' sync", tenant_id, api_id)

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
        environment = normalize_deployment_environment(environment) or environment

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
        gateway_ids = await self._resolve_target_gateway_ids(api_catalog, environment, gateway_ids)

        # 4. Preflight desired state against target adapter contracts before
        #    GatewayDeploymentService creates PENDING records and emits Kafka/SSE.
        preflight = await self._preflight_gateway_ids(api_catalog, gateway_ids)
        failed = [result for result in preflight if not result.deployable]
        if failed:
            raise ValueError(self._format_preflight_failure(failed))

        # 5. Deploy via existing GatewayDeploymentService (creates PENDING records + Kafka events)
        deployments = await self.deploy_svc.deploy_api(api_catalog.id, gateway_ids)

        # 6. Legacy mode: attempt inline sync for immediate UI feedback.
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

    async def preflight_deploy_api_to_env(
        self,
        tenant_id: str,
        api_identifier: str,
        environment: str,
        gateway_ids: list[UUID] | None = None,
        validate_promotion: bool = True,
    ) -> list[DeploymentPreflightResult]:
        """Validate that the desired state is deployable by each target gateway.

        This is a deterministic local contract check. It must run before any
        GatewayDeployment is created or any Kafka/SSE event is emitted.
        """
        api_catalog = await self._resolve_api_catalog(tenant_id, api_identifier)

        environment = normalize_deployment_environment(environment) or environment

        if validate_promotion and environment != "dev":
            has_promotion = await self._has_active_promotion(api_catalog.api_id, api_catalog.tenant_id, environment)
            if not has_promotion:
                raise ValueError(
                    f"API '{api_catalog.api_name}' has no active promotion to {environment}. "
                    f"Promote the API first before deploying to {environment}."
                )

        resolved_gateway_ids = await self._resolve_target_gateway_ids(api_catalog, environment, gateway_ids)
        return await self._preflight_gateway_ids(api_catalog, resolved_gateway_ids)

    async def preflight_api_to_gateways(
        self,
        api_catalog_id: UUID,
        gateway_ids: list[UUID],
    ) -> list[DeploymentPreflightResult]:
        """Validate an explicit API catalog entry against explicit gateway targets.

        Used by admin-level deployment entrypoints that already resolve target
        gateways in the request body. This keeps the ADF-G6/ADF-13b preflight
        contract in front of GatewayDeploymentService even when the caller does
        not go through the environment-aware /deploy route.
        """
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.id == api_catalog_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            raise ValueError("API catalog entry not found")

        return await self._preflight_gateway_ids(api_catalog, gateway_ids)

    async def _preflight_gateway_ids(
        self,
        api_catalog: APICatalog,
        gateway_ids: list[UUID],
    ) -> list[DeploymentPreflightResult]:
        desired_state = GatewayDeploymentService.build_desired_state(api_catalog)
        results: list[DeploymentPreflightResult] = []

        for gateway_id in gateway_ids:
            gateway = await self._get_gateway_or_raise(gateway_id)
            gateway_type = self._target_gateway_type_value(gateway)
            errors = self._validate_desired_state_for_gateway(desired_state, gateway_type, gateway)
            results.append(
                DeploymentPreflightResult(
                    gateway_id=str(gateway.id),
                    gateway_name=gateway.name,
                    target_gateway_type=gateway_type,
                    deployable=not errors,
                    errors=errors,
                )
            )

        return results

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
        target_environment = normalize_deployment_environment(target_environment) or target_environment
        assignments = await self.assignment_repo.list_auto_deploy(api_catalog.id, target_environment)
        if not assignments:
            raise ValueError(
                f"Promotion to {target_environment} cannot be marked deployed: no auto-deploy gateway "
                f"assignments exist for API '{api_catalog.api_name}'. Configure at least one target gateway."
            )

        gateway_ids = [a.gateway_id for a in assignments]
        preflight = await self._preflight_gateway_ids(api_catalog, gateway_ids)
        failed = [result for result in preflight if not result.deployable]
        if failed:
            raise ValueError(self._format_preflight_failure(failed))

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
                    deployment_mode=getattr(gateway, "deployment_mode", None),
                    topology=getattr(gateway, "topology", None),
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

    async def _resolve_target_gateway_ids(
        self,
        api_catalog: APICatalog,
        environment: str,
        gateway_ids: list[UUID] | None,
    ) -> list[UUID]:
        if gateway_ids is None:
            environment = normalize_deployment_environment(environment) or environment
            assignments = await self.assignment_repo.list_auto_deploy(api_catalog.id, environment)
            if not assignments:
                raise ValueError(
                    f"No gateway assignments with auto_deploy=True for API "
                    f"'{api_catalog.api_name}' in {environment}. "
                    f"Configure assignments or specify gateway_ids explicitly."
                )
            return [a.gateway_id for a in assignments]

        await self._validate_gateways_for_env(gateway_ids, environment)
        return gateway_ids

    async def _get_gateway_or_raise(self, gateway_id: UUID) -> GatewayInstance:
        result = await self.db.execute(select(GatewayInstance).where(GatewayInstance.id == gateway_id))
        gateway = result.scalar_one_or_none()
        if not gateway:
            raise ValueError(f"Gateway {gateway_id} not found")
        return gateway

    @staticmethod
    def _gateway_type_value(gateway_type) -> str:
        return str(getattr(gateway_type, "value", gateway_type))

    @staticmethod
    def _target_gateway_type_value(gateway: GatewayInstance) -> str:
        return normalize_gateway_topology(
            gateway_type=gateway.gateway_type,
            mode=gateway.mode,
            source=gateway.source,
            deployment_mode=gateway.deployment_mode,
            target_gateway_type=gateway.target_gateway_type,
            topology=gateway.topology,
            health_details=gateway.health_details,
            endpoints=gateway.endpoints,
            base_url=gateway.base_url,
            public_url=gateway.public_url,
            ui_url=gateway.ui_url,
            target_gateway_url=gateway.target_gateway_url,
            tags=gateway.tags,
            name=gateway.name,
        ).target_gateway_type

    @staticmethod
    def _format_preflight_failure(failed_results: list[DeploymentPreflightResult]) -> str:
        details = []
        for result in failed_results:
            for error in result.errors:
                details.append(f"{result.gateway_name}: {error.code} — {error.message}")
        return "Deployment preflight failed: " + "; ".join(details)

    def _validate_desired_state_for_gateway(
        self,
        desired_state: dict,
        gateway_type: str,
        gateway: GatewayInstance,
    ) -> list[DeploymentPreflightError]:
        if gateway_type != "webmethods":
            return []

        return self._validate_webmethods_openapi(
            desired_state.get("openapi_spec"),
            gateway_id=str(gateway.id),
            gateway_name=gateway.name,
            gateway_type=gateway_type,
        )

    @staticmethod
    def _validate_webmethods_openapi(
        openapi_spec,
        gateway_id: str,
        gateway_name: str,
        gateway_type: str,
    ) -> list[DeploymentPreflightError]:
        def error(code: str, message: str, path: str) -> DeploymentPreflightError:
            return DeploymentPreflightError(
                gateway_id=gateway_id,
                gateway_name=gateway_name,
                target_gateway_type=gateway_type,
                code=code,
                message=message,
                path=path,
            )

        if not isinstance(openapi_spec, dict):
            return [
                error(
                    "openapi_spec_missing",
                    "webMethods deployment requires a parsed OpenAPI object",
                    "openapi_spec",
                )
            ]

        version = openapi_spec.get("openapi") or openapi_spec.get("swagger")
        if not version:
            return [
                error(
                    "openapi_version_missing",
                    "OpenAPI spec must declare 'openapi' or 'swagger'",
                    "openapi_spec.openapi",
                )
            ]

        errors: list[DeploymentPreflightError] = []
        info = openapi_spec.get("info")
        if not isinstance(info, dict):
            errors.append(
                error("openapi_info_missing", "OpenAPI spec must include an info object", "openapi_spec.info")
            )
        else:
            if not info.get("title"):
                errors.append(
                    error("openapi_info_title_missing", "OpenAPI info.title is required", "openapi_spec.info.title")
                )
            if not info.get("version"):
                errors.append(
                    error(
                        "openapi_info_version_missing",
                        "OpenAPI info.version is required",
                        "openapi_spec.info.version",
                    )
                )

        paths = openapi_spec.get("paths")
        if not isinstance(paths, dict) or not paths:
            errors.append(
                error("openapi_paths_missing", "OpenAPI spec must include at least one path", "openapi_spec.paths")
            )
            return errors

        for path, path_item in paths.items():
            if not isinstance(path, str) or not path.startswith("/"):
                errors.append(
                    error(
                        "openapi_path_invalid",
                        "OpenAPI path keys must start with '/'",
                        f"openapi_spec.paths.{path}",
                    )
                )
                continue
            if not isinstance(path_item, dict):
                errors.append(
                    error(
                        "openapi_path_item_invalid",
                        "OpenAPI path item must be an object",
                        f"openapi_spec.paths.{path}",
                    )
                )
                continue

            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS:
                    continue
                operation_path = f"openapi_spec.paths.{path}.{method}"
                if not isinstance(operation, dict):
                    errors.append(
                        error(
                            "openapi_operation_invalid",
                            "OpenAPI operation must be an object",
                            operation_path,
                        )
                    )
                    continue
                responses = operation.get("responses")
                if not isinstance(responses, dict) or not responses:
                    errors.append(
                        error(
                            "openapi_operation_responses_missing",
                            "webMethods requires each OpenAPI operation to declare non-empty responses",
                            f"{operation_path}.responses",
                        )
                    )

        return errors

    async def _has_active_promotion(self, api_id: str, tenant_id: str, target_environment: str) -> bool:
        result = await self.db.execute(
            select(Promotion.id)
            .where(
                Promotion.api_id == api_id,
                Promotion.tenant_id == tenant_id,
                Promotion.target_environment.in_(deployment_environment_aliases(target_environment)),
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
                Promotion.target_environment.in_(deployment_environment_aliases(target_environment)),
                Promotion.status == PromotionStatus.PROMOTED.value,
            )
            .order_by(Promotion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _validate_gateways_for_env(self, gateway_ids: list[UUID], environment: str) -> None:
        for gw_id in gateway_ids:
            gateway = await self._get_gateway_or_raise(gw_id)
            if not deployment_environment_matches(gateway.environment, environment):
                raise ValueError(
                    f"Gateway '{gateway.name}' is in environment '{gateway.environment}', "
                    f"not '{environment}'. Select gateways matching the target environment."
                )
