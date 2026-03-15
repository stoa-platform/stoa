"""Internal API routes for gateway self-registration (ADR-028).

These endpoints are called by STOA gateways for auto-registration and heartbeat.
Not exposed on public ingress — internal traffic only.

Includes tool discovery endpoints (CAB-1817) authenticated via X-Gateway-Key
instead of user JWT, so sidecars (STOA Link) can discover tools without OIDC.
"""

import logging
from datetime import UTC, datetime
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
    requests_total: int | None = Field(default=None, description="Total requests served")
    error_rate: float | None = Field(default=None, description="Error rate (0.0-1.0)")


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
        existing.base_url = payload.admin_url
        existing.status = GatewayInstanceStatus.ONLINE
        existing.last_health_check = now
        existing.mode = normalized_mode
        existing.health_details = {**(existing.health_details or {}), **heartbeat_details}
        instance = await repo.update(existing)
        await db.commit()
        logger.info("Gateway re-registered: id=%s, name=%s", instance.id, instance.name)
        return instance

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

    # Store metrics in health_details
    instance.health_details = {
        **(instance.health_details or {}),
        "last_heartbeat": now.isoformat(),
        "uptime_seconds": payload.uptime_seconds,
        "routes_count": payload.routes_count,
        "policies_count": payload.policies_count,
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
        input_schema = _json.loads(t.input_schema) if t.input_schema else {"type": "object", "properties": {}, "required": []}
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
