"""Gateway Detail overview read-model service."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment, PolicySyncStatus
from src.models.gateway_instance import GatewayInstance
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.schemas.gateway_overview import (
    GatewayOverviewApi,
    GatewayOverviewApiSource,
    GatewayOverviewDataQuality,
    GatewayOverviewDataQualitySeverity,
    GatewayOverviewGateway,
    GatewayOverviewMetricsStatus,
    GatewayOverviewPolicy,
    GatewayOverviewPolicyBindingSource,
    GatewayOverviewPolicyTarget,
    GatewayOverviewResolvedConfig,
    GatewayOverviewResponse,
    GatewayOverviewRoutePreview,
    GatewayOverviewRuntime,
    GatewayOverviewRuntimeFreshness,
    GatewayOverviewRuntimeStatus,
    GatewayOverviewSource,
    GatewayOverviewSummary,
    GatewayOverviewSync,
    GatewayOverviewSyncStatus,
    GatewayOverviewVisibility,
    GatewayOverviewWarning,
)

SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "client_secret",
    "bearer",
    "jwt",
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class GatewayOverviewService:
    """Builds a safe Control Plane overview for a gateway."""

    def __init__(
        self,
        db: AsyncSession,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.now_fn = now_fn or (lambda: datetime.now(UTC))

    async def get_overview(self, gateway_id: UUID, user: Any) -> GatewayOverviewResponse:
        """Return an interpreted Gateway Detail overview."""
        now = _ensure_aware(self.now_fn())
        gateway = await self._load_gateway(gateway_id)
        if gateway is None:
            raise HTTPException(status_code=404, detail="Gateway instance not found")

        tenant_filter = self._tenant_filter(user)
        if not self._can_view_gateway(gateway, tenant_filter):
            raise HTTPException(status_code=403, detail="Access denied to this gateway")

        api_rows = await self._load_api_rows(gateway.id, tenant_filter)
        deployments = [row[0] for row in api_rows]
        catalog_by_id = {row[1].id: row[1] for row in api_rows}
        tenant_ids = {row[1].tenant_id for row in api_rows if row[1].tenant_id}
        if tenant_filter:
            tenant_ids = {tenant_filter}
        elif getattr(gateway, "tenant_id", None):
            tenant_ids.add(gateway.tenant_id)

        policy_rows = await self._load_policy_rows(
            gateway_id=gateway.id,
            catalog_ids=list(catalog_by_id),
            tenant_ids=list(tenant_ids),
            tenant_filter=tenant_filter,
        )

        deployment_by_api = {dep.api_catalog_id: dep for dep in deployments}
        policy_context = self._build_policy_context(policy_rows, gateway, catalog_by_id, deployment_by_api)
        apis = [
            self._build_api_overview(dep, catalog, policy_context.api_policy_counts.get(catalog.id, 0))
            for dep, catalog in api_rows
        ]
        policies = [
            self._build_policy_overview(policy, binding, gateway, catalog_by_id, policy_context.policy_statuses)
            for policy, binding in policy_context.effective_rows
        ]

        sync = self._build_sync(deployments)
        runtime, data_quality = self._build_runtime(gateway, now)
        summary = GatewayOverviewSummary(
            sync_status=sync.status,
            runtime_status=runtime.status,
            metrics_status=data_quality.metrics_status,
            apis_count=len(apis),
            expected_routes_count=sum(api.routes_count for api in apis),
            reported_routes_count=runtime.reported_routes_count,
            effective_policies_count=len(policies),
            reported_policies_count=runtime.reported_policies_count,
            failed_policies_count=sum(1 for policy in policies if policy.sync_status == GatewayOverviewSyncStatus.FAILED),
        )

        return GatewayOverviewResponse(
            generated_at=now,
            gateway=GatewayOverviewGateway(
                id=gateway.id,
                name=gateway.name,
                display_name=gateway.display_name,
                gateway_type=_enum_value(gateway.gateway_type),
                environment=gateway.environment,
                status=_enum_value(gateway.status),
                mode=gateway.mode,
                version=gateway.version,
            ),
            visibility=GatewayOverviewVisibility(
                rbac_scope="tenant" if tenant_filter else "admin",
                tenant_id=tenant_filter,
                filtered=tenant_filter is not None,
            ),
            source=self._build_source(api_rows),
            summary=summary,
            resolved_config=GatewayOverviewResolvedConfig(apis=apis, policies=policies),
            sync=sync,
            runtime=runtime,
            data_quality=data_quality,
        )

    async def _load_gateway(self, gateway_id: UUID) -> GatewayInstance | None:
        repo = GatewayInstanceRepository(self.db)
        return await repo.get_by_id(gateway_id)

    async def _load_api_rows(
        self,
        gateway_id: UUID,
        tenant_filter: str | None,
    ) -> list[tuple[GatewayDeployment, APICatalog]]:
        query = (
            select(GatewayDeployment, APICatalog)
            .join(APICatalog, GatewayDeployment.api_catalog_id == APICatalog.id)
            .where(
                GatewayDeployment.gateway_instance_id == gateway_id,
                APICatalog.deleted_at.is_(None),
            )
            .order_by(APICatalog.tenant_id, APICatalog.api_name, APICatalog.version)
        )
        if tenant_filter:
            query = query.where(APICatalog.tenant_id == tenant_filter)
        result = await self.db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def _load_policy_rows(
        self,
        gateway_id: UUID,
        catalog_ids: list[UUID],
        tenant_ids: list[str],
        tenant_filter: str | None,
    ) -> list[tuple[GatewayPolicy, GatewayPolicyBinding]]:
        conditions = [
            and_(
                GatewayPolicyBinding.gateway_instance_id == gateway_id,
                GatewayPolicyBinding.api_catalog_id.is_(None),
            )
        ]
        if catalog_ids:
            conditions.append(GatewayPolicyBinding.api_catalog_id.in_(catalog_ids))
        if tenant_ids:
            conditions.append(
                and_(
                    GatewayPolicyBinding.tenant_id.in_(tenant_ids),
                    GatewayPolicyBinding.api_catalog_id.is_(None),
                    GatewayPolicyBinding.gateway_instance_id.is_(None),
                )
            )

        query = (
            select(GatewayPolicy, GatewayPolicyBinding)
            .join(GatewayPolicyBinding, GatewayPolicy.id == GatewayPolicyBinding.policy_id)
            .where(
                GatewayPolicy.enabled.is_(True),
                GatewayPolicyBinding.enabled.is_(True),
                or_(*conditions),
            )
            .order_by(GatewayPolicy.priority, GatewayPolicy.name, GatewayPolicyBinding.created_at)
        )
        if tenant_filter:
            query = query.where(or_(GatewayPolicy.tenant_id == tenant_filter, GatewayPolicy.tenant_id.is_(None)))

        result = await self.db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    def _tenant_filter(self, user: Any) -> str | None:
        roles = getattr(user, "roles", []) or []
        if "cpi-admin" in roles:
            return None
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant-scoped user has no tenant")
        return tenant_id

    def _can_view_gateway(self, gateway: GatewayInstance, tenant_filter: str | None) -> bool:
        if tenant_filter is None:
            return True

        gateway_tenant = getattr(gateway, "tenant_id", None)
        if gateway_tenant and gateway_tenant != tenant_filter:
            return False

        visibility = getattr(gateway, "visibility", None)
        if visibility is None:
            return True
        if not isinstance(visibility, dict):
            return False
        tenant_ids = visibility.get("tenant_ids") or []
        return tenant_filter in tenant_ids

    def _build_source(self, api_rows: list[tuple[GatewayDeployment, APICatalog]]) -> GatewayOverviewSource:
        commits = {catalog.git_commit_sha for _, catalog in api_rows if catalog.git_commit_sha}
        loaded = [_coerce_datetime(getattr(catalog, "synced_at", None)) for _, catalog in api_rows]
        loaded = [dt for dt in loaded if dt is not None]
        return GatewayOverviewSource(
            control_plane_revision=next(iter(commits)) if len(commits) == 1 else None,
            last_loaded_at=max(loaded) if loaded else None,
        )

    def _build_api_overview(
        self,
        deployment: GatewayDeployment,
        catalog: APICatalog,
        policies_count: int,
    ) -> GatewayOverviewApi:
        desired_state = deployment.desired_state or {}
        backend = _safe_url(
            desired_state.get("backend_url")
            or _dict_get(catalog.api_metadata, "backend_url")
            or _dict_get(catalog.api_metadata, "url")
        )
        routes_count, routes_preview = self._route_preview(deployment, catalog, backend)
        return GatewayOverviewApi(
            tenant_id=catalog.tenant_id,
            api_id=catalog.api_id,
            api_catalog_id=catalog.id,
            name=catalog.api_name,
            version=catalog.version,
            source=GatewayOverviewApiSource(
                git_path=catalog.git_path,
                git_commit_sha=catalog.git_commit_sha,
                spec_hash=desired_state.get("spec_hash"),
            ),
            routes_count=routes_count,
            routes_preview=routes_preview,
            backend=backend,
            policies_count=policies_count,
            sync_status=self._deployment_sync_status(deployment),
            last_sync_at=_coerce_datetime(deployment.last_sync_success),
            last_error=deployment.sync_error or deployment.policy_sync_error,
        )

    def _route_preview(
        self,
        deployment: GatewayDeployment,
        catalog: APICatalog,
        backend: str | None,
    ) -> tuple[int, list[GatewayOverviewRoutePreview]]:
        desired_state = deployment.desired_state or {}
        spec = desired_state.get("openapi_spec") or catalog.openapi_spec or {}
        routes: list[GatewayOverviewRoutePreview] = []
        routes_count = 0

        paths = spec.get("paths") if isinstance(spec, dict) else None
        if isinstance(paths, dict):
            for path, path_item in sorted(paths.items()):
                if not isinstance(path_item, dict):
                    continue
                for method in sorted(path_item):
                    if method.lower() not in HTTP_METHODS:
                        continue
                    routes_count += 1
                    if len(routes) < 3:
                        routes.append(
                            GatewayOverviewRoutePreview(
                                method=method.upper(),
                                path=str(path),
                                backend=backend,
                            )
                        )

        if routes_count > 0:
            return routes_count, routes

        methods = desired_state.get("methods") if isinstance(desired_state.get("methods"), list) else ["ANY"]
        api_name = desired_state.get("api_name") or catalog.api_name
        route_path = desired_state.get("path") or desired_state.get("base_path") or f"/apis/{catalog.tenant_id}/{api_name}"
        return 1, [
            GatewayOverviewRoutePreview(
                method=str(methods[0]).upper(),
                path=str(route_path),
                backend=backend,
            )
        ]

    def _build_policy_context(
        self,
        policy_rows: list[tuple[GatewayPolicy, GatewayPolicyBinding]],
        gateway: GatewayInstance,
        catalog_by_id: dict[UUID, APICatalog],
        deployment_by_api: dict[UUID, GatewayDeployment],
    ) -> _PolicyContext:
        # A policy may match through multiple bindings. Keep one effective row,
        # preferring the most specific binding, then priority order from SQL.
        by_policy: dict[UUID, tuple[GatewayPolicy, GatewayPolicyBinding]] = {}
        for policy, binding in policy_rows:
            if not bool(policy.enabled) or not bool(binding.enabled):
                continue
            existing = by_policy.get(policy.id)
            if existing is None or _binding_specificity(binding) > _binding_specificity(existing[1]):
                by_policy[policy.id] = (policy, binding)

        effective_rows = sorted(
            by_policy.values(),
            key=lambda row: (row[0].priority, row[0].name),
        )
        api_policy_counts: dict[UUID, int] = defaultdict(int)
        policy_statuses: dict[UUID, GatewayOverviewSyncStatus] = {}

        for policy, binding in effective_rows:
            binding_scope = _binding_scope(binding)
            target_api_ids = _binding_api_ids(binding, catalog_by_id)
            if binding_scope == "api" and binding.api_catalog_id:
                api_policy_counts[binding.api_catalog_id] += 1
            elif binding_scope == "gateway":
                for api_id in catalog_by_id:
                    api_policy_counts[api_id] += 1
            elif binding_scope == "tenant":
                for api_id, catalog in catalog_by_id.items():
                    if catalog.tenant_id == binding.tenant_id:
                        api_policy_counts[api_id] += 1

            policy_statuses[policy.id] = self._aggregate_policy_sync_status(
                [deployment_by_api[api_id] for api_id in target_api_ids if api_id in deployment_by_api]
            )

        return _PolicyContext(
            effective_rows=effective_rows,
            api_policy_counts=api_policy_counts,
            policy_statuses=policy_statuses,
        )

    def _aggregate_policy_sync_status(
        self,
        deployments: list[GatewayDeployment],
    ) -> GatewayOverviewSyncStatus:
        if not deployments:
            return GatewayOverviewSyncStatus.UNKNOWN
        statuses = [self._deployment_sync_status(dep) for dep in deployments]
        if GatewayOverviewSyncStatus.FAILED in statuses:
            return GatewayOverviewSyncStatus.FAILED
        if GatewayOverviewSyncStatus.DRIFT in statuses:
            return GatewayOverviewSyncStatus.DRIFT
        if GatewayOverviewSyncStatus.PENDING in statuses:
            return GatewayOverviewSyncStatus.PENDING
        if all(status == GatewayOverviewSyncStatus.IN_SYNC for status in statuses):
            return GatewayOverviewSyncStatus.IN_SYNC
        return GatewayOverviewSyncStatus.UNKNOWN

    def _build_policy_overview(
        self,
        policy: GatewayPolicy,
        binding: GatewayPolicyBinding,
        gateway: GatewayInstance,
        catalog_by_id: dict[UUID, APICatalog],
        policy_statuses: dict[UUID, GatewayOverviewSyncStatus],
    ) -> GatewayOverviewPolicy:
        scope = _binding_scope(binding)
        target = _policy_target(scope, binding, gateway, catalog_by_id)
        return GatewayOverviewPolicy(
            id=policy.id,
            name=policy.name,
            type=_enum_value(policy.policy_type),
            scope=scope,
            target=target,
            enabled=bool(policy.enabled),
            priority=policy.priority,
            summary=_policy_summary(_enum_value(policy.policy_type), policy.config or {}),
            sync_status=policy_statuses.get(policy.id, GatewayOverviewSyncStatus.UNKNOWN),
            source_binding=GatewayOverviewPolicyBindingSource(
                id=binding.id,
                scope=scope,
                target_id=target.id,
            ),
        )

    def _build_sync(self, deployments: list[GatewayDeployment]) -> GatewayOverviewSync:
        status = self._overall_sync_status(deployments)
        desired_generations = [_int_or_none(getattr(dep, "desired_generation", None)) for dep in deployments]
        applied_generations = [_int_or_none(getattr(dep, "synced_generation", None)) for dep in deployments]
        desired_generations = [value for value in desired_generations if value is not None]
        applied_generations = [value for value in applied_generations if value is not None]
        reconciled_times = [
            _coerce_datetime(dep.last_sync_success) or _coerce_datetime(dep.actual_at) or _coerce_datetime(dep.last_sync_attempt)
            for dep in deployments
        ]
        reconciled_times = [dt for dt in reconciled_times if dt is not None]
        steps = []
        for dep in deployments:
            for step in dep.sync_steps or []:
                item = dict(step)
                item.setdefault("deployment_id", str(dep.id))
                item.setdefault("api_catalog_id", str(dep.api_catalog_id))
                steps.append(item)

        return GatewayOverviewSync(
            desired_generation=max(desired_generations) if desired_generations else None,
            applied_generation=min(applied_generations) if applied_generations else None,
            status=status,
            drift=status == GatewayOverviewSyncStatus.DRIFT,
            last_reconciled_at=max(reconciled_times) if reconciled_times else None,
            last_error=next((dep.sync_error or dep.policy_sync_error for dep in deployments if dep.sync_error or dep.policy_sync_error), None),
            steps=steps,
        )

    def _overall_sync_status(self, deployments: list[GatewayDeployment]) -> GatewayOverviewSyncStatus:
        if not deployments:
            return GatewayOverviewSyncStatus.IN_SYNC
        statuses = [self._deployment_sync_status(dep) for dep in deployments]
        if GatewayOverviewSyncStatus.FAILED in statuses:
            return GatewayOverviewSyncStatus.FAILED
        if GatewayOverviewSyncStatus.DRIFT in statuses:
            return GatewayOverviewSyncStatus.DRIFT
        if GatewayOverviewSyncStatus.PENDING in statuses:
            return GatewayOverviewSyncStatus.PENDING
        if all(status == GatewayOverviewSyncStatus.IN_SYNC for status in statuses):
            return GatewayOverviewSyncStatus.IN_SYNC
        return GatewayOverviewSyncStatus.UNKNOWN

    def _deployment_sync_status(self, deployment: GatewayDeployment) -> GatewayOverviewSyncStatus:
        sync_status = _enum_value(deployment.sync_status)
        policy_status = _enum_value(getattr(deployment, "policy_sync_status", None))
        if sync_status == DeploymentSyncStatus.ERROR.value or policy_status in {
            PolicySyncStatus.ERROR.value,
            PolicySyncStatus.PARTIAL.value,
        }:
            return GatewayOverviewSyncStatus.FAILED
        if sync_status == DeploymentSyncStatus.DRIFTED.value:
            return GatewayOverviewSyncStatus.DRIFT
        if sync_status in {
            DeploymentSyncStatus.PENDING.value,
            DeploymentSyncStatus.SYNCING.value,
            DeploymentSyncStatus.DELETING.value,
        }:
            return GatewayOverviewSyncStatus.PENDING

        desired_generation = _int_or_none(getattr(deployment, "desired_generation", None))
        synced_generation = _int_or_none(getattr(deployment, "synced_generation", None))
        if desired_generation is not None and synced_generation is not None and desired_generation != synced_generation:
            return GatewayOverviewSyncStatus.PENDING
        if sync_status == DeploymentSyncStatus.SYNCED.value:
            return GatewayOverviewSyncStatus.IN_SYNC
        return GatewayOverviewSyncStatus.UNKNOWN

    def _build_runtime(
        self,
        gateway: GatewayInstance,
        now: datetime,
    ) -> tuple[GatewayOverviewRuntime, GatewayOverviewDataQuality]:
        health_details = gateway.health_details if isinstance(gateway.health_details, dict) else {}
        heartbeat_at = _coerce_datetime(health_details.get("last_heartbeat")) or _coerce_datetime(gateway.last_health_check)
        heartbeat_age = int((now - heartbeat_at).total_seconds()) if heartbeat_at else None
        stale_after = settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS
        freshness = GatewayOverviewRuntimeFreshness.MISSING
        warnings: list[GatewayOverviewWarning] = []

        if heartbeat_at is None:
            runtime_status = GatewayOverviewRuntimeStatus.OFFLINE
            warnings.append(
                GatewayOverviewWarning(
                    code="runtime_heartbeat_missing",
                    severity=GatewayOverviewDataQualitySeverity.WARNING,
                    message="No heartbeat has been reported by this gateway",
                )
            )
        elif heartbeat_age is not None and heartbeat_age > stale_after:
            freshness = GatewayOverviewRuntimeFreshness.STALE
            runtime_status = GatewayOverviewRuntimeStatus.STALE
            warnings.append(
                GatewayOverviewWarning(
                    code="runtime_heartbeat_stale",
                    severity=GatewayOverviewDataQualitySeverity.WARNING,
                    message="Gateway heartbeat data is stale",
                )
            )
        else:
            freshness = GatewayOverviewRuntimeFreshness.FRESH
            runtime_status = _runtime_status_from_gateway(gateway.status)

        runtime = GatewayOverviewRuntime(
            status=runtime_status,
            last_heartbeat_at=heartbeat_at,
            heartbeat_age_seconds=heartbeat_age,
            version=gateway.version,
            mode=gateway.mode,
            uptime_seconds=_int_or_none(health_details.get("uptime_seconds")),
            reported_routes_count=_int_or_none(health_details.get("routes_count")),
            reported_policies_count=_int_or_none(health_details.get("policies_count")),
            mcp_tools_count=_int_or_none(
                health_details.get("mcp_tools_count", health_details.get("discovered_apis_count"))
            ),
            requests_total=_int_or_none(health_details.get("requests_total")),
            error_rate=_float_or_none(health_details.get("error_rate")),
            memory_usage_bytes=_int_or_none(
                health_details.get("memory_usage_bytes", health_details.get("memory_rss_bytes"))
            ),
        )

        metrics_status = _metrics_status(runtime)
        if metrics_status == GatewayOverviewMetricsStatus.UNAVAILABLE:
            warnings.append(
                GatewayOverviewWarning(
                    code="runtime_metrics_unavailable",
                    severity=GatewayOverviewDataQualitySeverity.WARNING,
                    message="Runtime metrics are not available for this gateway",
                )
            )
        elif metrics_status == GatewayOverviewMetricsStatus.PARTIAL:
            warnings.append(
                GatewayOverviewWarning(
                    code="runtime_metrics_partial",
                    severity=GatewayOverviewDataQualitySeverity.INFO,
                    message="Some runtime metrics are not available for this gateway",
                )
            )

        data_quality = GatewayOverviewDataQuality(
            runtime_freshness=freshness,
            heartbeat_stale_after_seconds=stale_after,
            metrics_status=metrics_status,
            metrics_window_seconds=_int_or_none(health_details.get("metrics_window_seconds")) or 300,
            warnings=warnings,
        )
        return runtime, data_quality


class _PolicyContext:
    def __init__(
        self,
        effective_rows: list[tuple[GatewayPolicy, GatewayPolicyBinding]],
        api_policy_counts: dict[UUID, int],
        policy_statuses: dict[UUID, GatewayOverviewSyncStatus],
    ) -> None:
        self.effective_rows = effective_rows
        self.api_policy_counts = api_policy_counts
        self.policy_statuses = policy_statuses


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if value is None:
        return ""
    return str(value)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, str):
        try:
            return _ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dict_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return _redact_string(value)

    hostname = parts.hostname or ""
    netloc = hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    query = urlencode(
        [
            (key, "[REDACTED]" if _is_sensitive_key(key) else val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower().replace("_", "-")
    return any(part in lower for part in SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    lower = value.lower()
    if any(part in lower for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(str(key)) else _redact(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _policy_summary(policy_type: str, config: dict) -> str:
    safe = _redact(config or {})
    if policy_type == "rate_limit":
        limit = (
            safe.get("requests_per_minute")
            or safe.get("requests_per_min")
            or safe.get("rpm")
            or safe.get("limit")
        )
        if limit is not None:
            return f"Rate limit: {limit} req/min per consumer"
        return "Rate limit configured"
    if policy_type == "jwt_validation":
        return "JWT policy configured"
    if policy_type == "cors":
        origins = _count_values(safe.get("origins") or safe.get("allow_origins"))
        methods = safe.get("methods") or safe.get("allow_methods") or []
        methods_text = "/".join(str(method).upper() for method in methods[:3]) if isinstance(methods, list) else "configured"
        if origins is not None:
            return f"CORS: {origins} origins, {methods_text}"
        return "CORS policy configured"
    if policy_type == "ip_filter":
        cidrs = _count_values(safe.get("allowlist") or safe.get("allowed_cidrs") or safe.get("cidrs"))
        if cidrs is not None:
            return f"IP filter: {cidrs} CIDRs allowed"
        return "IP filter configured"
    if policy_type == "logging":
        return "Logging policy configured"
    if policy_type == "caching":
        return "Caching policy configured"
    if policy_type == "transform":
        return "Transform policy configured"
    return "Policy configured"


def _count_values(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, str) and value:
        return 1
    return None


def _binding_scope(binding: GatewayPolicyBinding) -> str:
    if binding.api_catalog_id is not None:
        return "api"
    if binding.gateway_instance_id is not None:
        return "gateway"
    return "tenant"


def _binding_specificity(binding: GatewayPolicyBinding) -> int:
    scope = _binding_scope(binding)
    return {"tenant": 1, "gateway": 2, "api": 3}.get(scope, 0)


def _binding_api_ids(
    binding: GatewayPolicyBinding,
    catalog_by_id: dict[UUID, APICatalog],
) -> list[UUID]:
    scope = _binding_scope(binding)
    if scope == "api" and binding.api_catalog_id in catalog_by_id:
        return [binding.api_catalog_id]
    if scope == "gateway":
        return list(catalog_by_id)
    return [
        api_id
        for api_id, catalog in catalog_by_id.items()
        if catalog.tenant_id == binding.tenant_id
    ]


def _policy_target(
    scope: str,
    binding: GatewayPolicyBinding,
    gateway: GatewayInstance,
    catalog_by_id: dict[UUID, APICatalog],
) -> GatewayOverviewPolicyTarget:
    if scope == "api" and binding.api_catalog_id in catalog_by_id:
        catalog = catalog_by_id[binding.api_catalog_id]
        return GatewayOverviewPolicyTarget(type="api", id=str(catalog.id), name=catalog.api_name)
    if scope == "gateway":
        return GatewayOverviewPolicyTarget(type="gateway", id=str(gateway.id), name=gateway.name)
    return GatewayOverviewPolicyTarget(type="tenant", id=binding.tenant_id, name=binding.tenant_id)


def _runtime_status_from_gateway(status: Any) -> GatewayOverviewRuntimeStatus:
    value = _enum_value(status)
    if value == "online":
        return GatewayOverviewRuntimeStatus.HEALTHY
    if value == "degraded":
        return GatewayOverviewRuntimeStatus.DEGRADED
    if value == "offline":
        return GatewayOverviewRuntimeStatus.OFFLINE
    return GatewayOverviewRuntimeStatus.UNKNOWN


def _metrics_status(runtime: GatewayOverviewRuntime) -> GatewayOverviewMetricsStatus:
    values: Iterable[Any] = (
        runtime.requests_total,
        runtime.error_rate,
        runtime.memory_usage_bytes,
    )
    available = [value is not None for value in values]
    if not any(available):
        return GatewayOverviewMetricsStatus.UNAVAILABLE
    if all(available):
        return GatewayOverviewMetricsStatus.AVAILABLE
    return GatewayOverviewMetricsStatus.PARTIAL
