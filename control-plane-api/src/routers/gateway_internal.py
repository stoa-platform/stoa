"""Internal API routes for gateway self-registration (ADR-028).

These endpoints are called by STOA gateways for auto-registration and heartbeat.
Not exposed on public ingress — internal traffic only.
"""
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.gateway_instance import (
    GatewayInstance,
    GatewayInstanceStatus,
    GatewayType,
)
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.schemas.gateway import GatewayInstanceResponse

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
    """Map gateway mode to GatewayType enum."""
    mode_lower = mode.lower().replace("_", "").replace("-", "")
    if mode_lower == "sidecar":
        return GatewayType.STOA_SIDECAR
    # All other modes (edge_mcp, proxy, shadow) are full STOA gateways
    return GatewayType.STOA


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

    # Derive deterministic instance name
    instance_name = _derive_instance_name(payload.hostname, payload.mode, payload.environment)
    gateway_type = _mode_to_gateway_type(payload.mode)

    logger.info(
        "Gateway registration request: name=%s, type=%s, version=%s, capabilities=%s",
        instance_name,
        gateway_type.value,
        payload.version,
        payload.capabilities,
    )

    # Check if already registered (upsert pattern)
    existing = await repo.get_by_name(instance_name)
    now = datetime.now(UTC)

    if existing:
        # Update existing registration
        existing.version = payload.version
        existing.capabilities = payload.capabilities
        existing.base_url = payload.admin_url
        existing.status = GatewayInstanceStatus.ONLINE
        existing.last_health_check = now
        existing.health_details = {
            "registered_at": now.isoformat(),
            "mode": payload.mode,
            "hostname": payload.hostname,
        }
        instance = await repo.update(existing)
        await db.commit()
        logger.info("Gateway re-registered: id=%s, name=%s", instance.id, instance.name)
    else:
        # Create new registration
        instance = GatewayInstance(
            name=instance_name,
            display_name=f"STOA Gateway ({payload.mode})",
            gateway_type=gateway_type,
            environment=payload.environment,
            tenant_id=payload.tenant_id,
            base_url=payload.admin_url,
            auth_config={"type": "gateway_key"},  # Internal auth via heartbeat
            status=GatewayInstanceStatus.ONLINE,
            last_health_check=now,
            health_details={
                "registered_at": now.isoformat(),
                "mode": payload.mode,
                "hostname": payload.hostname,
            },
            capabilities=payload.capabilities,
            version=payload.version,
            tags=[f"mode:{payload.mode}", "auto-registered"],
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

    # TODO: Query pending deployments and policies for this gateway
    return {
        "gateway_id": str(instance.id),
        "name": instance.name,
        "environment": instance.environment,
        "tenant_id": instance.tenant_id,
        "pending_deployments": [],  # Future: from GatewayDeployment table
        "pending_policies": [],  # Future: from GatewayPolicy table
    }
