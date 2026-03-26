"""Internal API routes for gateway self-registration (ADR-028).

These endpoints are called by STOA gateways for auto-registration and heartbeat.
Not exposed on public ingress — internal traffic only.

Includes tool discovery endpoints (CAB-1817) authenticated via X-Gateway-Key
instead of user JWT, so sidecars (STOA Link) can discover tools without OIDC.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.gateway_instance import (
    GatewayInstance,
    GatewayInstanceStatus,
    GatewayType,
)
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.repositories.gateway_policy import GatewayPolicyRepository
from src.schemas.contract import McpToolDefinition, TenantToolsResponse
from src.schemas.gateway import GatewayInstanceResponse
from src.services.uac_tool_generator import UacToolGenerator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/internal/gateways",
    tags=["Gateway Internal"],
)


# --- Route Reload Endpoint (CAB-1828) ---


class CleanupResult(BaseModel):
    """Result of the manual gateway cleanup."""

    purged_count: int = Field(..., description="Number of stale instances soft-deleted")
    purged_instances: list[str] = Field(default_factory=list, description="Names of purged instances")


@router.post("/cleanup", response_model=CleanupResult)
async def cleanup_stale_gateways(
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger cleanup of stale gateway instances (CAB-1897).

    Soft-deletes instances that have been OFFLINE for longer than
    GATEWAY_PURGE_AFTER_DAYS (default 7 days). Protected instances are skipped.
    """
    _validate_gateway_key(x_gateway_key)

    purge_cutoff = datetime.now(UTC) - timedelta(days=settings.GATEWAY_PURGE_AFTER_DAYS)

    from sqlalchemy import select

    stmt = select(GatewayInstance).where(
        GatewayInstance.status == GatewayInstanceStatus.OFFLINE,
        GatewayInstance.last_health_check < purge_cutoff,
        GatewayInstance.deleted_at.is_(None),
        GatewayInstance.protected.is_(False),
    )
    result = await db.execute(stmt)
    stale_gateways = result.scalars().all()

    now = datetime.now(UTC)
    purged_names = []
    for gw in stale_gateways:
        gw.deleted_at = now
        gw.deleted_by = "system:manual-cleanup"
        purged_names.append(gw.name)
        logger.info("Manual cleanup: purged stale gateway %s (%s)", gw.name, gw.id)

    await db.commit()

    return CleanupResult(purged_count=len(purged_names), purged_instances=purged_names)


class GatewayRouteItem(BaseModel):
    """Route in stoa-gateway ApiRoute format for hot-reload."""

    id: str
    name: str
    tenant_id: str
    path_prefix: str
    backend_url: str
    methods: list[str] = []
    spec_hash: str = ""
    activated: bool = True


@router.get("/routes", response_model=list[GatewayRouteItem])
async def list_gateway_routes(
    gateway_name: str | None = Query(None, description="Filter by gateway instance name"),
    db: AsyncSession = Depends(get_db),
    x_gateway_key: str | None = Header(None),
):
    """Return all synced deployment routes in stoa-gateway ApiRoute format.

    Used by the gateway route hot-reload loop (CAB-1828) to pull the full
    route table from the control plane. No JWT auth — uses X-Gateway-Key.
    """
    expected_key = getattr(settings, "GATEWAY_ADMIN_KEY", None)
    if expected_key and x_gateway_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid gateway key")

    from src.adapters.stoa.mappers import map_api_spec_to_stoa
    from src.models.gateway_deployment import DeploymentSyncStatus

    deploy_repo = GatewayDeploymentRepository(db)

    # Get all SYNCED + PENDING deployments (PENDING = recently deployed, should be on gateway)
    deployments = await deploy_repo.list_by_statuses(
        [
            DeploymentSyncStatus.SYNCED,
            DeploymentSyncStatus.PENDING,
        ]
    )

    routes = []
    for dep in deployments:
        ds = dep.desired_state or {}
        tenant_id = ds.get("tenant_id", "")
        route = map_api_spec_to_stoa(ds, tenant_id)
        if route.get("backend_url"):  # Skip routes without a backend
            routes.append(GatewayRouteItem(**route))

    return routes


# --- Pydantic Schemas ---


class GatewayRegistration(BaseModel):
    """Self-registration payload from gateway."""

    hostname: str = Field(..., description="Gateway hostname (e.g., 'stoa-gateway-7f8b9c')")
    mode: str = Field(..., description="Gateway mode: edge_mcp, sidecar, proxy, shadow")
    version: str = Field(..., description="Gateway software version (e.g., '0.1.0')")
    environment: str = Field(default="dev", description="Deployment environment")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Gateway capabilities: rest, mcp, sse, oidc, rate_limiting, ext_authz, metering",
    )
    admin_url: str = Field(..., description="Gateway admin API URL for CP to call back")
    tenant_id: str | None = Field(default=None, description="Optional tenant restriction")


class HeartbeatPayload(BaseModel):
    """Heartbeat payload with optional metrics."""

    uptime_seconds: int = Field(..., description="Gateway uptime in seconds")
    routes_count: int = Field(default=0, description="Number of registered routes")
    policies_count: int = Field(default=0, description="Number of active policies")
    discovered_apis: int = Field(default=0, description="Number of discovered APIs")
    requests_total: int | None = Field(default=None, description="Total requests served")
    error_rate: float | None = Field(default=None, description="Error rate (0.0-1.0)")


class DiscoveredAPIItem(BaseModel):
    """A single API discovered by stoa-connect on a gateway."""

    name: str = Field(..., description="API/service name")
    version: str = Field(default="", description="API version")
    backend_url: str = Field(default="", description="Backend URL")
    paths: list[str] = Field(default_factory=list, description="Exposed paths")
    methods: list[str] = Field(default_factory=list, description="HTTP methods")
    policies: list[str] = Field(default_factory=list, description="Active policies")
    is_active: bool = Field(default=True, description="Whether the API is active")


class DiscoveryPayload(BaseModel):
    """Discovery report from stoa-connect."""

    apis: list[DiscoveredAPIItem] = Field(default_factory=list, description="Discovered APIs")


# --- Helper Functions ---


def _validate_gateway_key(x_gateway_key: str) -> None:
    """Validate the X-Gateway-Key header against configured keys."""
    valid_keys = settings.gateway_api_keys_list
    if not valid_keys:
        raise HTTPException(
            status_code=503,
            detail="Gateway registration disabled (no GATEWAY_API_KEYS configured)",
        )
    if x_gateway_key not in valid_keys:
        logger.warning("Invalid gateway key attempted registration")
        raise HTTPException(status_code=401, detail="Invalid gateway key")


def _derive_instance_name(hostname: str, mode: str, environment: str) -> str:
    """Derive deterministic instance name from registration data."""
    # Normalize mode to remove underscores for cleaner names
    mode_clean = mode.replace("_", "")
    return f"{hostname}-{mode_clean}-{environment}"


def _mode_to_gateway_type(mode: str) -> GatewayType:
    """Map gateway mode to GatewayType enum (ADR-024)."""
    mode_lower = mode.lower().replace("_", "-")
    mode_map = {
        "edge-mcp": GatewayType.STOA_EDGE_MCP,
        "edgemcp": GatewayType.STOA_EDGE_MCP,
        "mcp": GatewayType.STOA_EDGE_MCP,
        "sidecar": GatewayType.STOA_SIDECAR,
        "proxy": GatewayType.STOA_PROXY,
        "shadow": GatewayType.STOA_SHADOW,
        "connect": GatewayType.STOA,
    }
    return mode_map.get(mode_lower, GatewayType.STOA)


def _normalize_mode(mode: str) -> str:
    """Normalize mode string to canonical form (ADR-024)."""
    mode_lower = mode.lower().replace("_", "-")
    mode_map = {
        "edge-mcp": "edge-mcp",
        "edgemcp": "edge-mcp",
        "edge_mcp": "edge-mcp",
        "mcp": "edge-mcp",
        "sidecar": "sidecar",
        "proxy": "proxy",
        "shadow": "shadow",
        "connect": "connect",
    }
    return mode_map.get(mode_lower, "edge-mcp")


# --- Endpoints ---


@router.post("/register", response_model=GatewayInstanceResponse, status_code=201)
async def register_gateway(
    payload: GatewayRegistration,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Gateway self-registration endpoint.

    Called by STOA gateways at startup. Creates or updates the gateway instance
    record based on the deterministic name derived from hostname + mode + environment.

    Returns the assigned gateway ID for subsequent heartbeat calls.
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)

    # Derive deterministic instance name and normalize mode
    instance_name = _derive_instance_name(payload.hostname, payload.mode, payload.environment)
    gateway_type = _mode_to_gateway_type(payload.mode)
    normalized_mode = _normalize_mode(payload.mode)

    logger.info(
        "Gateway registration request: name=%s, type=%s, version=%s, capabilities=%s",
        instance_name,
        gateway_type.value,
        payload.version,
        payload.capabilities,
    )

    now = datetime.now(UTC)
    heartbeat_details = {
        "registered_at": now.isoformat(),
        "mode": normalized_mode,
        "hostname": payload.hostname,
    }

    # 1. Check if already registered by name (re-registration after restart)
    existing = await repo.get_by_name(instance_name)
    if existing:
        existing.version = payload.version
        existing.capabilities = payload.capabilities
        # Preserve manually-set HTTPS base_url over auto-detected internal URL
        if not (existing.base_url and existing.base_url.startswith("https://")):
            existing.base_url = payload.admin_url
        existing.status = GatewayInstanceStatus.ONLINE
        existing.last_health_check = now
        existing.mode = normalized_mode
        existing.health_details = {**(existing.health_details or {}), **heartbeat_details}
        instance = await repo.update(existing)
        await db.commit()
        logger.info("Gateway re-registered: id=%s, name=%s", instance.id, instance.name)
        return instance

    # 1b. Cancel-and-replace: soft-delete stale self_register entries with same
    #     mode+env but different name (hostname changed after container recreation).
    #     This prevents duplicate gateways in the Console UI.
    stale_entries = await repo.find_self_registered_by_mode_env(
        mode=normalized_mode,
        environment=payload.environment,
        exclude_name=instance_name,
    )
    for stale in stale_entries:
        await repo.soft_delete(stale, deleted_by=f"replaced-by:{instance_name}")
        logger.info(
            "Gateway cancel-and-replace: soft-deleted stale entry id=%s, name=%s (replaced by %s)",
            stale.id,
            stale.name,
            instance_name,
        )

    # 2. Check if ArgoCD reconciler already created an entry for this type+env.
    #    Adopt it instead of creating a duplicate (Phase 4: ArgoCD as source of truth).
    argocd_entry = await repo.get_by_source_and_type(
        source="argocd",
        gateway_type=gateway_type,
        environment=payload.environment,
    )
    if argocd_entry:
        argocd_entry.version = payload.version
        argocd_entry.capabilities = payload.capabilities
        argocd_entry.base_url = payload.admin_url
        argocd_entry.status = GatewayInstanceStatus.ONLINE
        argocd_entry.last_health_check = now
        argocd_entry.mode = normalized_mode
        argocd_entry.health_details = {**(argocd_entry.health_details or {}), **heartbeat_details}
        instance = await repo.update(argocd_entry)
        await db.commit()
        logger.info(
            "Gateway adopted ArgoCD entry: id=%s, argocd_name=%s, hostname=%s",
            instance.id,
            instance.name,
            payload.hostname,
        )
        return instance

    # 3. No existing entry — create with source=self_register (non-ArgoCD deployments)
    instance = GatewayInstance(
        name=instance_name,
        display_name=f"STOA Gateway ({normalized_mode})",
        gateway_type=gateway_type,
        environment=payload.environment,
        tenant_id=payload.tenant_id,
        base_url=payload.admin_url,
        auth_config={"type": "gateway_key"},
        status=GatewayInstanceStatus.ONLINE,
        last_health_check=now,
        mode=normalized_mode,
        health_details=heartbeat_details,
        capabilities=payload.capabilities,
        version=payload.version,
        source="self_register",
        tags=[f"mode:{normalized_mode}", "auto-registered"],
    )
    instance = await repo.create(instance)
    await db.commit()
    logger.info("Gateway registered: id=%s, name=%s", instance.id, instance.name)

    return instance


@router.post("/{gateway_id}/heartbeat", status_code=204)
async def gateway_heartbeat(
    gateway_id: UUID,
    payload: HeartbeatPayload,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Gateway heartbeat endpoint.

    Called every 30s by STOA gateways to maintain ONLINE status.
    If no heartbeat received for 90s, gateway is marked OFFLINE by the health worker.
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)
    instance = await repo.get_by_id(gateway_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    # Update health check timestamp and metrics
    now = datetime.now(UTC)
    instance.last_health_check = now
    instance.status = GatewayInstanceStatus.ONLINE

    # Store metrics in health_details.
    # CAB-1916: heartbeat stores `discovered_apis_count` (int), never
    # `discovered_apis` — that key is reserved for the discovery array.
    instance.health_details = {
        **(instance.health_details or {}),
        "last_heartbeat": now.isoformat(),
        "uptime_seconds": payload.uptime_seconds,
        "routes_count": payload.routes_count,
        "policies_count": payload.policies_count,
        "discovered_apis_count": payload.discovered_apis,
        "requests_total": payload.requests_total,
        "error_rate": payload.error_rate,
    }

    await repo.update(instance)
    await db.commit()

    logger.debug(
        "Gateway heartbeat: id=%s, uptime=%ds, routes=%d",
        gateway_id,
        payload.uptime_seconds,
        payload.routes_count,
    )


@router.post("/{gateway_id}/discovery", status_code=200)
async def report_discovery(
    gateway_id: UUID,
    payload: DiscoveryPayload,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Receive API discovery report from stoa-connect.

    Called periodically by stoa-connect agents to report APIs/services
    discovered on the local gateway's admin API.
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)
    instance = await repo.get_by_id(gateway_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    # Store discovery snapshot in health_details
    now = datetime.now(UTC)
    discovered_apis = [api.model_dump() for api in payload.apis]

    instance.health_details = {
        **(instance.health_details or {}),
        "last_discovery": now.isoformat(),
        "discovered_apis_count": len(payload.apis),
        "discovered_apis": discovered_apis,
    }

    await repo.update(instance)
    await db.commit()

    logger.info(
        "Gateway discovery report: id=%s, apis_count=%d",
        gateway_id,
        len(payload.apis),
    )

    return {
        "gateway_id": str(gateway_id),
        "apis_received": len(payload.apis),
    }


class SyncedPolicyResult(BaseModel):
    """Result of syncing a single policy on the gateway."""

    policy_id: str = Field(..., description="Policy ID from CP")
    status: str = Field(..., description="Sync result: applied, removed, failed")
    error: str | None = Field(default=None, description="Error message if failed")


class SyncAckPayload(BaseModel):
    """Payload from stoa-connect reporting policy sync results."""

    synced_policies: list[SyncedPolicyResult] = Field(default_factory=list, description="Sync results per policy")
    sync_timestamp: str = Field(..., description="ISO timestamp of sync completion")


@router.post("/{gateway_id}/sync-ack", status_code=200)
async def sync_ack(
    gateway_id: UUID,
    payload: SyncAckPayload,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge policy sync results from stoa-connect (CAB-1817 Phase 3).

    Called by stoa-connect after applying/removing policies on the local gateway.
    Stores sync results in the gateway's health_details for observability.
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)
    instance = await repo.get_by_id(gateway_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    # Store sync results in health_details
    synced = [r.model_dump() for r in payload.synced_policies]
    applied = sum(1 for r in payload.synced_policies if r.status == "applied")
    removed = sum(1 for r in payload.synced_policies if r.status == "removed")
    failed = sum(1 for r in payload.synced_policies if r.status == "failed")

    instance.health_details = {
        **(instance.health_details or {}),
        "last_sync": payload.sync_timestamp,
        "last_sync_results": synced,
        "sync_applied": applied,
        "sync_removed": removed,
        "sync_failed": failed,
    }

    await repo.update(instance)
    await db.commit()

    logger.info(
        "Gateway sync-ack: id=%s, applied=%d, removed=%d, failed=%d",
        gateway_id,
        applied,
        removed,
        failed,
    )

    return {
        "gateway_id": str(gateway_id),
        "applied": applied,
        "removed": removed,
        "failed": failed,
    }


class InternalToolDef(BaseModel):
    """Tool definition in the format expected by the gateway (ToolsListResponse)."""

    name: str
    description: str
    inputSchema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})


class InternalToolsListResponse(BaseModel):
    """Response matching the gateway's ToolsListResponse format."""

    tools: list[InternalToolDef]


@router.get("/tools", response_model=InternalToolsListResponse)
async def get_internal_tools(
    tenant_id: str = Query(default="", description="Tenant ID (optional filter)"),
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Internal tool discovery for gateways/sidecars (CAB-1817).

    Returns UAC-generated tools in the gateway's expected format (ToolsListResponse),
    authenticated via X-Gateway-Key. Allows STOA Link sidecars to discover tools
    without OIDC client credentials.
    """
    _validate_gateway_key(x_gateway_key)

    if not tenant_id:
        return InternalToolsListResponse(tools=[])

    generator = UacToolGenerator(db)
    tools = await generator.get_tools_for_tenant(tenant_id)

    import json as _json

    result = []
    for t in tools:
        if not t.enabled:
            continue
        input_schema = (
            _json.loads(t.input_schema) if t.input_schema else {"type": "object", "properties": {}, "required": []}
        )
        result.append(
            InternalToolDef(
                name=t.tool_name,
                description=t.description or "",
                inputSchema=input_schema,
            )
        )

    return InternalToolsListResponse(tools=result)


@router.get("/tools/generated", response_model=TenantToolsResponse)
async def get_internal_generated_tools(
    tenant_id: str = Query(..., description="Tenant ID"),
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Internal tool discovery for gateways/sidecars (CAB-1817).

    Returns UAC-generated tools for a tenant, authenticated via X-Gateway-Key
    instead of user JWT. This allows STOA Link sidecars to discover tools
    without needing OIDC client credentials.
    """
    _validate_gateway_key(x_gateway_key)

    generator = UacToolGenerator(db)
    tools = await generator.get_tools_for_tenant(tenant_id)

    return TenantToolsResponse(
        tenant_id=tenant_id,
        tools=[_internal_tool_to_response(t) for t in tools],
        total=len(tools),
    )


def _internal_tool_to_response(tool) -> McpToolDefinition:
    """Convert ORM tool to response schema (reused from contracts.py)."""
    import json as _json

    return McpToolDefinition(
        tool_name=tool.tool_name,
        description=tool.description,
        input_schema=_json.loads(tool.input_schema) if tool.input_schema else None,
        output_schema=_json.loads(tool.output_schema) if tool.output_schema else None,
        backend_url=tool.backend_url,
        http_method=tool.http_method,
        path_pattern=tool.path_pattern,
        version=tool.version,
        spec_hash=tool.spec_hash,
        enabled=tool.enabled,
    )


@router.get("/{gateway_id}/config")
async def get_gateway_config(
    gateway_id: UUID,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Get configuration for a registered gateway.

    Future: Return pending deployments, policies, etc. for the gateway to apply.
    Currently returns basic gateway info.
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)
    instance = await repo.get_by_id(gateway_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    # Query pending deployments for this gateway
    deployment_repo = GatewayDeploymentRepository(db)
    pending_deployments = await deployment_repo.list_by_gateway(
        gateway_instance_id=instance.id,
        sync_status=None,  # Return all statuses so gateway knows full picture
    )

    # Query applicable policies for this gateway
    policy_repo = GatewayPolicyRepository(db)
    tenant_id = instance.tenant_id or ""
    policies = await policy_repo.list_all(tenant_id=tenant_id if tenant_id else None)

    return {
        "gateway_id": str(instance.id),
        "name": instance.name,
        "environment": instance.environment,
        "tenant_id": instance.tenant_id,
        "pending_deployments": [
            {
                "id": str(d.id),
                "api_catalog_id": str(d.api_catalog_id),
                "sync_status": d.sync_status.value,
                "desired_state": d.desired_state,
                "sync_attempts": d.sync_attempts,
            }
            for d in pending_deployments
        ],
        "pending_policies": [
            {
                "id": str(p.id),
                "name": p.name,
                "policy_type": p.policy_type.value,
                "config": p.config,
                "priority": p.priority,
                "enabled": p.enabled,
            }
            for p in policies
        ],
    }
