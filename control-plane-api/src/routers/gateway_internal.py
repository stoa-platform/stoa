"""Internal API routes for gateway self-registration (ADR-028).

These endpoints are called by STOA gateways for auto-registration and heartbeat.
Not exposed on public ingress — internal traffic only.

Includes tool discovery endpoints (CAB-1817) authenticated via X-Gateway-Key
instead of user JWT, so sidecars (STOA Link) can discover tools without OIDC.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

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
from src.services.gateway_topology import GatewayTopology, normalize_gateway_topology
from src.services.promotion_service import PromotionService
from src.services.uac_tool_generator import UacToolGenerator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/internal/gateways",
    tags=["Gateway Internal"],
)

_PROD_ENVIRONMENTS = {"prod", "production"}
_PROD_WEBMETHODS_HOSTS = {
    "vps-wm.gostoa.dev",
    "vps-wm-ui.gostoa.dev",
    "webmethods.gostoa.dev",
}
_UI_ENDPOINT_KEYS = {"ui_url", "uiUrl", "console_url", "consoleUrl", "web_ui_url", "webUiUrl"}
_TARGET_ENDPOINT_KEYS = {"target_gateway_url", "targetGatewayUrl", "target_url", "targetUrl"}


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
    api_id: str = ""
    deployment_id: str = ""
    name: str
    tenant_id: str
    path_prefix: str
    backend_url: str
    methods: list[str] = []
    spec_hash: str = ""
    openapi_spec: dict | None = None
    activated: bool = True
    generation: int = 1


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

    # Get SYNCED + PENDING deployments, filtered by gateway if specified.
    # Without filtering, a stoa-connect instance syncs routes from ALL gateways
    # to its local gateway — causing cross-gateway pollution (CAB-1938).
    statuses = [DeploymentSyncStatus.SYNCED, DeploymentSyncStatus.PENDING]

    if gateway_name:
        gw_repo = GatewayInstanceRepository(db)
        gateway = await gw_repo.get_by_name(gateway_name)
        if not gateway:
            gateway = await gw_repo.get_self_registered_by_hostname(gateway_name)
        if gateway:
            deployments = await deploy_repo.list_by_statuses_and_gateway(statuses, gateway.id)
        else:
            deployments = []
    else:
        deployments = await deploy_repo.list_by_statuses(statuses)

    routes = []
    for dep in deployments:
        ds = dep.desired_state or {}
        tenant_id = ds.get("tenant_id", "")
        route = map_api_spec_to_stoa(ds, tenant_id)
        if route.get("backend_url"):  # Skip routes without a backend
            item = GatewayRouteItem(**route, deployment_id=str(dep.id), generation=dep.desired_generation or 1)
            routes.append(item)

    return routes


# --- Pydantic Schemas ---


class GatewayRegistration(BaseModel):
    """Self-registration payload from gateway."""

    hostname: str = Field(..., description="Gateway hostname (e.g., 'stoa-gateway-7f8b9c')")
    mode: str = Field(..., description="Gateway runtime mode: edge_mcp, sidecar, proxy, shadow, connect")
    version: str = Field(..., description="Gateway software version (e.g., '0.1.0')")
    environment: str = Field(default="dev", description="Deployment environment")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Gateway capabilities: rest, mcp, sse, oidc, rate_limiting, ext_authz, metering",
    )
    admin_url: str = Field(..., description="Gateway admin API URL for CP to call back")
    tenant_id: str | None = Field(default=None, description="Optional tenant restriction")
    target_gateway_url: str | None = Field(
        default=None,
        description="URL of the third-party gateway managed by this Link/Connect (e.g. webMethods admin URL)",
    )
    public_url: str | None = Field(
        default=None,
        description="Public DNS URL of this gateway for Console display (CAB-1940)",
    )
    ui_url: str | None = Field(
        default=None,
        description="Web UI URL of the third-party gateway (e.g. webMethods console at :9072)",
    )
    endpoints: dict[str, str] | None = Field(
        default=None,
        description="Structured endpoint map: public_url, internal_url, admin_url, health_url",
    )
    deployment_mode: str | None = Field(
        default=None,
        description="Canonical topology mode: edge, connect, or sidecar",
    )
    target_gateway_type: str | None = Field(
        default=None,
        description="Gateway technology STOA fronts or controls",
    )
    topology: str | None = Field(
        default=None,
        description="Execution topology: native-edge, remote-agent, or same-pod",
    )
    topology_proof: dict | None = Field(
        default=None,
        description="Evidence required for deployment_mode=sidecar same-pod classification",
    )


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


def _host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return urlparse(value).hostname
    except ValueError:
        return None


def _drop_endpoint_keys(endpoints: dict | None, keys: set[str]) -> dict:
    if not isinstance(endpoints, dict):
        return {}
    return {key: value for key, value in endpoints.items() if key not in keys}


def _is_webmethods_registration(
    payload: GatewayRegistration,
    *,
    instance_name: str,
    target_gateway_type: str | None,
) -> bool:
    target = (payload.target_gateway_type or target_gateway_type or "").lower().replace("-", "_")
    search_space = " ".join(
        value
        for value in [
            target,
            instance_name,
            payload.hostname,
            payload.target_gateway_url or "",
            payload.public_url or "",
            payload.admin_url,
        ]
        if value
    ).lower()
    return "webmethods" in search_space or "wm" in search_space


def _apply_registration_urls(instance: GatewayInstance, payload: GatewayRegistration) -> None:
    """Apply URL fields from registration and clear stale prod wM URLs in non-prod."""
    sent_fields = payload.model_fields_set
    for field_name in ("target_gateway_url", "public_url", "ui_url"):
        if field_name in sent_fields:
            setattr(instance, field_name, getattr(payload, field_name))

    environment = (payload.environment or instance.environment or "").lower()
    if environment in _PROD_ENVIRONMENTS:
        return

    if not _is_webmethods_registration(
        payload,
        instance_name=instance.name,
        target_gateway_type=instance.target_gateway_type,
    ):
        return

    if _host(instance.ui_url) in _PROD_WEBMETHODS_HOSTS:
        instance.ui_url = None
        instance.endpoints = _drop_endpoint_keys(instance.endpoints, _UI_ENDPOINT_KEYS)
    if _host(instance.target_gateway_url) in _PROD_WEBMETHODS_HOSTS:
        instance.target_gateway_url = None
        instance.endpoints = _drop_endpoint_keys(instance.endpoints, _TARGET_ENDPOINT_KEYS)


def _registration_topology(
    payload: GatewayRegistration,
    *,
    gateway_type: GatewayType,
    normalized_mode: str,
    instance_name: str,
    health_details: dict,
    source: str,
    base_url: str,
    public_url: str | None,
    ui_url: str | None,
    target_gateway_url: str | None,
    endpoints: dict | None = None,
    deployment_mode: str | None = None,
    target_gateway_type: str | None = None,
    topology: str | None = None,
) -> GatewayTopology:
    """Normalize topology from registration payload plus preserved DB values."""
    base_endpoints = endpoints if isinstance(endpoints, dict) else {}
    merged_endpoints = {**base_endpoints, **(payload.endpoints or {})}
    return normalize_gateway_topology(
        gateway_type=gateway_type,
        mode=normalized_mode,
        source=source,
        deployment_mode=payload.deployment_mode or deployment_mode,
        target_gateway_type=payload.target_gateway_type or target_gateway_type,
        topology=payload.topology or topology,
        health_details=health_details,
        endpoints=merged_endpoints,
        base_url=base_url,
        public_url=public_url,
        ui_url=ui_url,
        target_gateway_url=target_gateway_url,
        tags=[f"mode:{normalized_mode}", "auto-registered"],
        name=instance_name,
    )


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
    if payload.topology_proof:
        heartbeat_details["topology_proof"] = payload.topology_proof

    normalized_topology = _registration_topology(
        payload,
        gateway_type=gateway_type,
        normalized_mode=normalized_mode,
        instance_name=instance_name,
        health_details=heartbeat_details,
        source="self_register",
        base_url=payload.admin_url,
        public_url=payload.public_url,
        ui_url=payload.ui_url,
        target_gateway_url=payload.target_gateway_url,
    )

    # 1. Check if already registered by name (re-registration after restart)
    existing = await repo.get_by_name(instance_name)
    if existing:
        existing.version = payload.version
        existing.capabilities = payload.capabilities
        # Preserve manually-set HTTPS base_url over auto-detected internal URL
        if not (existing.base_url and existing.base_url.startswith("https://")):
            existing.base_url = payload.admin_url
        _apply_registration_urls(existing, payload)
        existing.status = GatewayInstanceStatus.ONLINE
        existing.last_health_check = now
        existing.mode = normalized_mode
        existing.health_details = {**(existing.health_details or {}), **heartbeat_details}
        existing_topology = _registration_topology(
            payload,
            gateway_type=gateway_type,
            normalized_mode=normalized_mode,
            instance_name=instance_name,
            health_details=existing.health_details,
            source=existing.source,
            base_url=existing.base_url,
            public_url=existing.public_url,
            ui_url=existing.ui_url,
            target_gateway_url=existing.target_gateway_url,
            endpoints=existing.endpoints,
            deployment_mode=existing.deployment_mode,
            target_gateway_type=existing.target_gateway_type,
            topology=existing.topology,
        )
        existing.deployment_mode = existing_topology.deployment_mode
        existing.target_gateway_type = existing_topology.target_gateway_type
        existing.topology = existing_topology.topology
        existing.endpoints = existing_topology.endpoints
        instance = await repo.update(existing)
        await db.commit()
        logger.info("Gateway re-registered: id=%s, name=%s", instance.id, instance.name)
        return instance

    # 1c. Resurrect: if a soft-deleted entry exists with the same name, restore it
    #     instead of creating a new one (would violate unique constraint on name).
    #     Happens when a gateway re-registers after auto-purge (CAB-1897) or manual cleanup.
    deleted_entry = await repo.get_by_name_including_deleted(instance_name)
    if deleted_entry:
        deleted_entry.deleted_at = None
        deleted_entry.deleted_by = None
        deleted_entry.version = payload.version
        deleted_entry.capabilities = payload.capabilities
        deleted_entry.base_url = payload.admin_url
        _apply_registration_urls(deleted_entry, payload)
        deleted_entry.status = GatewayInstanceStatus.ONLINE
        deleted_entry.last_health_check = now
        deleted_entry.mode = normalized_mode
        deleted_entry.health_details = {**(deleted_entry.health_details or {}), **heartbeat_details}
        deleted_topology = _registration_topology(
            payload,
            gateway_type=gateway_type,
            normalized_mode=normalized_mode,
            instance_name=instance_name,
            health_details=deleted_entry.health_details,
            source=deleted_entry.source,
            base_url=deleted_entry.base_url,
            public_url=deleted_entry.public_url,
            ui_url=deleted_entry.ui_url,
            target_gateway_url=deleted_entry.target_gateway_url,
            endpoints=deleted_entry.endpoints,
            deployment_mode=deleted_entry.deployment_mode,
            target_gateway_type=deleted_entry.target_gateway_type,
            topology=deleted_entry.topology,
        )
        deleted_entry.deployment_mode = deleted_topology.deployment_mode
        deleted_entry.target_gateway_type = deleted_topology.target_gateway_type
        deleted_entry.topology = deleted_topology.topology
        deleted_entry.endpoints = deleted_topology.endpoints
        instance = await repo.update(deleted_entry)
        await db.commit()
        logger.info(
            "Gateway resurrected from soft-delete: id=%s, name=%s",
            instance.id,
            instance.name,
        )
        return instance

    # 1b. Cancel-and-replace: soft-delete stale self_register entries with same
    #     mode+env but different name (hostname changed after container recreation).
    #     This prevents duplicate gateways in the Console UI.
    stale_entries = await repo.find_self_registered_by_mode_env(
        mode=normalized_mode,
        environment=payload.environment,
        exclude_name=instance_name,
        target_gateway_type=normalized_topology.target_gateway_type,
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
        _apply_registration_urls(argocd_entry, payload)
        argocd_entry.status = GatewayInstanceStatus.ONLINE
        argocd_entry.last_health_check = now
        argocd_entry.mode = normalized_mode
        argocd_entry.health_details = {**(argocd_entry.health_details or {}), **heartbeat_details}
        argocd_topology = _registration_topology(
            payload,
            gateway_type=gateway_type,
            normalized_mode=normalized_mode,
            instance_name=argocd_entry.name,
            health_details=argocd_entry.health_details,
            source=argocd_entry.source,
            base_url=argocd_entry.base_url,
            public_url=argocd_entry.public_url,
            ui_url=argocd_entry.ui_url,
            target_gateway_url=argocd_entry.target_gateway_url,
            endpoints=argocd_entry.endpoints,
            deployment_mode=argocd_entry.deployment_mode,
            target_gateway_type=argocd_entry.target_gateway_type,
            topology=argocd_entry.topology,
        )
        argocd_entry.deployment_mode = argocd_topology.deployment_mode
        argocd_entry.target_gateway_type = argocd_topology.target_gateway_type
        argocd_entry.topology = argocd_topology.topology
        argocd_entry.endpoints = argocd_topology.endpoints
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
        target_gateway_url=payload.target_gateway_url,
        public_url=payload.public_url,
        ui_url=payload.ui_url,
        endpoints=normalized_topology.endpoints,
        deployment_mode=normalized_topology.deployment_mode,
        target_gateway_type=normalized_topology.target_gateway_type,
        topology=normalized_topology.topology,
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


class SyncedRouteResult(BaseModel):
    """Result of syncing a single route deployment on the gateway."""

    deployment_id: str = Field(..., description="GatewayDeployment UUID")
    status: str = Field(..., description="Sync result: applied or failed")
    error: str | None = Field(default=None, description="Error message if failed")
    steps: list[dict] | None = Field(default=None, description="Ordered sync step trace (optional)")
    generation: int | None = Field(default=None, description="Generation that was synced (CAB-1950)")


class RouteSyncAckPayload(BaseModel):
    """Payload from stoa-connect reporting route sync results."""

    synced_routes: list[SyncedRouteResult] = Field(default_factory=list, description="Sync results per route")
    sync_timestamp: str = Field(..., description="ISO timestamp of sync completion")


@router.post("/{gateway_id}/route-sync-ack", status_code=200)
async def route_sync_ack(
    gateway_id: UUID,
    payload: RouteSyncAckPayload,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge route sync results from stoa-connect.

    Called by stoa-connect after pushing routes to the local gateway.
    Updates GatewayDeployment sync_status based on the results.
    """
    _validate_gateway_key(x_gateway_key)

    deploy_repo = GatewayDeploymentRepository(db)
    now = datetime.now(UTC)

    processed = 0
    not_found = 0

    from src.models.gateway_deployment import DeploymentSyncStatus

    for result in payload.synced_routes:
        try:
            dep_uuid = UUID(result.deployment_id)
        except ValueError:
            logger.warning("route-sync-ack: invalid deployment_id=%s", result.deployment_id)
            not_found += 1
            continue

        deployment = await deploy_repo.get_by_id(dep_uuid)
        if not deployment:
            logger.warning(
                "route-sync-ack: deployment not found id=%s gateway=%s",
                result.deployment_id,
                gateway_id,
            )
            not_found += 1
            continue

        # Validate that this gateway owns this deployment (CAB-1938).
        # Without this check, a stoa-connect instance can ack deployments
        # belonging to another gateway, marking them SYNCED on the wrong host.
        if deployment.gateway_instance_id != gateway_id:
            logger.warning(
                "route-sync-ack: gateway mismatch deploy=%s owns=%s ack_from=%s — skipping",
                result.deployment_id,
                deployment.gateway_instance_id,
                gateway_id,
            )
            not_found += 1
            continue

        # Build the merged step trace, but only persist it once the ack is accepted
        # as canonical. Failed re-acks for an already synced generation are
        # connectivity observations, not deployment-state changes.
        merged_steps = None
        if result.steps is not None:
            from src.services.sync_step_tracker import SyncStepTracker

            # Prepend CP-side event_emitted step to agent-reported steps
            cp_tracker = SyncStepTracker()
            cp_tracker.start("event_emitted")
            cp_tracker.complete("event_emitted", detail="deployment dispatched to agent")
            merged_steps = cp_tracker.to_list() + result.steps

        # CAB-1950: reject stale generation acks
        if result.generation is not None and result.generation < deployment.desired_generation:
            logger.debug(
                "route-sync-ack: stale generation %d < desired %d for deployment %s, skipping",
                result.generation,
                deployment.desired_generation,
                result.deployment_id,
            )
            continue

        desired_generation = deployment.desired_generation if isinstance(deployment.desired_generation, int) else 1
        synced_generation = deployment.synced_generation if isinstance(deployment.synced_generation, int) else 0

        if (
            result.status == "failed"
            and deployment.sync_status == DeploymentSyncStatus.SYNCED
            and deployment.last_sync_success is not None
            and synced_generation >= desired_generation
        ):
            logger.info(
                "route-sync-ack: preserving synced deployment %s after failed re-ack for generation %s",
                result.deployment_id,
                result.generation,
            )
            if result.generation is not None:
                deployment.attempted_generation = max(deployment.attempted_generation, result.generation)
            deployment.last_sync_attempt = now
            await deploy_repo.update(deployment)
            processed += 1
            continue

        if result.status == "applied":
            deployment.sync_status = DeploymentSyncStatus.SYNCED
            deployment.last_sync_success = now
            deployment.sync_error = None
            if merged_steps is not None:
                deployment.sync_steps = merged_steps
            if result.generation is not None:
                deployment.synced_generation = result.generation
                deployment.attempted_generation = result.generation
        elif result.status == "failed":
            deployment.sync_status = DeploymentSyncStatus.ERROR
            if result.generation is not None:
                deployment.attempted_generation = result.generation
            if merged_steps is not None:
                deployment.sync_steps = merged_steps
            # Derive sync_error from step trace if available, else use scalar error
            if merged_steps:
                tracker = SyncStepTracker.from_list(merged_steps)
                deployment.sync_error = tracker.first_error() or result.error
            else:
                deployment.sync_error = result.error
        else:
            logger.warning("route-sync-ack: unknown status=%s for deployment=%s", result.status, result.deployment_id)
            continue

        deployment.last_sync_attempt = now
        await deploy_repo.update(deployment)
        processed += 1

    await db.commit()

    # Check if any updated deployments are linked to a promotion
    promotion_ids_to_check: set[UUID] = set()
    for result in payload.synced_routes:
        try:
            dep_uuid = UUID(result.deployment_id)
        except ValueError:
            continue
        dep = await deploy_repo.get_by_id(dep_uuid)
        if dep and dep.promotion_id:
            promotion_ids_to_check.add(dep.promotion_id)

    for promo_id in promotion_ids_to_check:
        try:
            promotion_svc = PromotionService(db)
            await promotion_svc.check_promotion_completion(promo_id)
            await db.commit()
        except Exception as e:
            logger.warning("Promotion completion check failed for %s: %s", promo_id, e)

    logger.info(
        "Gateway route-sync-ack: id=%s, processed=%d, not_found=%d",
        gateway_id,
        processed,
        not_found,
    )

    return {"processed": processed, "not_found": not_found}


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


# --- SSE endpoint for STOA Link agents (ADR-059) ---

LINK_EVENT_TYPES = ["sync-deployment", "sync-policy", "undeploy"]


async def _link_event_generator(
    request: Request, gateway_id: str, event_types: list[str] | None = None
) -> AsyncGenerator[dict, None]:
    """Generate SSE events for a specific gateway (ADR-059)."""
    from src.events.event_bus import event_bus

    sub = event_bus.subscribe(
        tenant_id="*",
        gateway_id=gateway_id,
        event_types=event_types or LINK_EVENT_TYPES,
    )
    try:
        async for event in event_bus.listen(sub):
            if await request.is_disconnected():
                break
            data = event.get("data", {})
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(data) if isinstance(data, dict) else data,
            }
    except asyncio.CancelledError:
        pass
    finally:
        event_bus.unsubscribe(sub)


@router.get("/{gateway_id}/events")
async def stream_gateway_events(
    gateway_id: UUID,
    request: Request,
    x_gateway_key: str = Header(..., alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """SSE stream of deployment events for a specific gateway (ADR-059).

    Used by STOA Link agents to receive real-time deployment notifications
    instead of polling /config. Events include:
    - sync-deployment: new deployment to apply
    - sync-policy: policy update
    - undeploy: API removal

    Authentication: X-Gateway-Key header (same as other internal endpoints).
    """
    _validate_gateway_key(x_gateway_key)

    repo = GatewayInstanceRepository(db)
    instance = await repo.get_by_id(gateway_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Gateway instance not found")

    return EventSourceResponse(_link_event_generator(request, str(gateway_id)))
