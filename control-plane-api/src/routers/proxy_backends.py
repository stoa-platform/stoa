"""Proxy backends router — manage internal API backends for STOA Gateway proxy (CAB-1725).

RBAC: cpi-admin full access, tenant-admin/devops/viewer read-only.
"""

import logging
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.proxy_backend import ProxyBackend, ProxyBackendAuthType, ProxyBackendStatus
from ..repositories.proxy_backend import ProxyBackendRepository
from ..schemas.proxy_backend import (
    ProxyBackendCreate,
    ProxyBackendHealthStatus,
    ProxyBackendListResponse,
    ProxyBackendResponse,
    ProxyBackendUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/proxy-backends", tags=["Proxy Backends"])

# Cached health results (backend_name -> (result, timestamp))
_health_cache: dict[str, tuple[ProxyBackendHealthStatus, float]] = {}
HEALTH_CACHE_TTL = 30.0  # seconds


def _require_admin(user: User) -> None:
    """Require cpi-admin role for write operations."""
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("", response_model=ProxyBackendListResponse)
async def list_proxy_backends(
    active_only: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all registered proxy backends."""
    repo = ProxyBackendRepository(db)
    backends, total = await repo.list_all(active_only=active_only)

    return ProxyBackendListResponse(
        items=[ProxyBackendResponse.model_validate(b) for b in backends],
        total=total,
    )


@router.get("/{backend_id}", response_model=ProxyBackendResponse)
async def get_proxy_backend(
    backend_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific proxy backend by ID."""
    repo = ProxyBackendRepository(db)
    backend = await repo.get_by_id(backend_id)

    if not backend:
        raise HTTPException(status_code=404, detail="Proxy backend not found")

    return ProxyBackendResponse.model_validate(backend)


@router.post("", response_model=ProxyBackendResponse, status_code=201)
async def create_proxy_backend(
    request: ProxyBackendCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new proxy backend. Requires cpi-admin role."""
    _require_admin(user)

    repo = ProxyBackendRepository(db)

    # Check for duplicate name
    existing = await repo.get_by_name(request.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Proxy backend with name '{request.name}' already exists",
        )

    backend = ProxyBackend(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        base_url=request.base_url,
        health_endpoint=request.health_endpoint,
        auth_type=ProxyBackendAuthType(request.auth_type),
        credential_ref=request.credential_ref,
        rate_limit_rpm=request.rate_limit_rpm,
        circuit_breaker_enabled=request.circuit_breaker_enabled,
        fallback_direct=request.fallback_direct,
        timeout_secs=request.timeout_secs,
        status=ProxyBackendStatus.ACTIVE,
        is_active=True,
    )

    backend = await repo.create(backend)
    logger.info(f"Created proxy backend {backend.name} (id={backend.id}) by={user.email}")

    return ProxyBackendResponse.model_validate(backend)


@router.put("/{backend_id}", response_model=ProxyBackendResponse)
async def update_proxy_backend(
    backend_id: UUID,
    request: ProxyBackendUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a proxy backend. Requires cpi-admin role."""
    _require_admin(user)

    repo = ProxyBackendRepository(db)
    backend = await repo.get_by_id(backend_id)

    if not backend:
        raise HTTPException(status_code=404, detail="Proxy backend not found")

    # Update fields (only non-None values)
    if request.display_name is not None:
        backend.display_name = request.display_name
    if request.description is not None:
        backend.description = request.description
    if request.base_url is not None:
        backend.base_url = request.base_url
    if request.health_endpoint is not None:
        backend.health_endpoint = request.health_endpoint
    if request.auth_type is not None:
        backend.auth_type = ProxyBackendAuthType(request.auth_type)
    if request.credential_ref is not None:
        backend.credential_ref = request.credential_ref
    if request.rate_limit_rpm is not None:
        backend.rate_limit_rpm = request.rate_limit_rpm
    if request.circuit_breaker_enabled is not None:
        backend.circuit_breaker_enabled = request.circuit_breaker_enabled
    if request.fallback_direct is not None:
        backend.fallback_direct = request.fallback_direct
    if request.timeout_secs is not None:
        backend.timeout_secs = request.timeout_secs
    if request.is_active is not None:
        backend.is_active = request.is_active
        backend.status = ProxyBackendStatus.ACTIVE if request.is_active else ProxyBackendStatus.DISABLED

    backend = await repo.update(backend)
    logger.info(f"Updated proxy backend {backend.name} by={user.email}")

    return ProxyBackendResponse.model_validate(backend)


@router.delete("/{backend_id}", status_code=204)
async def delete_proxy_backend(
    backend_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a proxy backend. Requires cpi-admin role."""
    _require_admin(user)

    repo = ProxyBackendRepository(db)
    backend = await repo.get_by_id(backend_id)

    if not backend:
        raise HTTPException(status_code=404, detail="Proxy backend not found")

    await repo.delete(backend)
    logger.info(f"Deleted proxy backend {backend.name} (id={backend_id}) by={user.email}")


@router.get("/{backend_id}/health", response_model=ProxyBackendHealthStatus)
async def check_proxy_backend_health(
    backend_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check health of a proxy backend. Cached for 30s."""
    repo = ProxyBackendRepository(db)
    backend = await repo.get_by_id(backend_id)

    if not backend:
        raise HTTPException(status_code=404, detail="Proxy backend not found")

    if not backend.health_endpoint:
        return ProxyBackendHealthStatus(
            backend_name=backend.name,
            healthy=True,
            error="No health endpoint configured",
            checked_at=datetime.now(UTC),
        )

    # Check cache
    now = time.monotonic()
    cached = _health_cache.get(backend.name)
    if cached and (now - cached[1]) < HEALTH_CACHE_TTL:
        return cached[0]

    # Perform health check
    health_url = f"{backend.base_url.rstrip('/')}{backend.health_endpoint}"
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url)

        latency_ms = (time.monotonic() - start) * 1000
        result = ProxyBackendHealthStatus(
            backend_name=backend.name,
            healthy=resp.status_code < 400,
            status_code=resp.status_code,
            latency_ms=round(latency_ms, 2),
            checked_at=datetime.now(UTC),
        )
    except httpx.HTTPError as e:
        latency_ms = (time.monotonic() - start) * 1000
        result = ProxyBackendHealthStatus(
            backend_name=backend.name,
            healthy=False,
            latency_ms=round(latency_ms, 2),
            error=str(e)[:200],
            checked_at=datetime.now(UTC),
        )

    # Cache result
    _health_cache[backend.name] = (result, now)
    return result
