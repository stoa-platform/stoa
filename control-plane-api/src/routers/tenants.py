"""Tenants router - Multi-tenant management using database"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Permission, Role, User, get_current_user, require_permission
from ..database import get_db
from ..models.tenant import Tenant, TenantProvisioningStatus, TenantStatus
from ..repositories.tenant import TenantRepository
from ..schemas.tenant import (
    TenantCreate,
    TenantProvisioningStatusResponse,
    TenantResponse,
    TenantUpdate,
)
from ..schemas.tenant_dr import TenantExportResponse
from ..services.cache_service import tenant_cache
from ..services.kafka_service import Topics, kafka_service
from ..services.tenant_dr_service import TenantExportService
from ..services.tenant_provisioning_service import deprovision_tenant, provision_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"])


def _tenant_to_response(tenant: Tenant, api_count: int = 0, app_count: int = 0) -> TenantResponse:
    """Convert database Tenant model to API response."""
    settings = tenant.settings or {}
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        display_name=tenant.name,
        description=tenant.description or "",
        owner_email=settings.get("owner_email", ""),
        status=tenant.status,
        provisioning_status=tenant.provisioning_status or "pending",
        api_count=api_count,
        application_count=app_count,
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
    )


@router.get("", response_model=list[TenantResponse])
async def list_tenants(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    List tenants from database.

    - CPI Admin: See all tenants
    - Others: See only their own tenant
    """
    try:
        repo = TenantRepository(db)
        is_admin = Role.CPI_ADMIN in user.roles

        tenants = await repo.list_for_user(tenant_id=user.tenant_id, is_admin=is_admin)

        return [_tenant_to_response(t) for t in tenants]

    except Exception as e:
        logger.error(f"Failed to list tenants: {e}")
        return []


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get tenant by ID from database (cached, TTL 30s)."""
    # Check access
    if Role.CPI_ADMIN not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check cache first
    cache_key = f"tenant:{tenant_id}"
    cached = await tenant_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        repo = TenantRepository(db)
        tenant = await repo.get_by_id(tenant_id)

        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        response = _tenant_to_response(tenant)
        await tenant_cache.set(cache_key, response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tenant")


@router.get("/{tenant_id}/provisioning-status", response_model=TenantProvisioningStatusResponse)
async def get_provisioning_status(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant provisioning status."""
    if Role.CPI_ADMIN not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    repo = TenantRepository(db)
    tenant = await repo.get_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantProvisioningStatusResponse(
        tenant_id=tenant.id,
        provisioning_status=tenant.provisioning_status or "pending",
        provisioning_error=tenant.provisioning_error,
        provisioning_started_at=(
            tenant.provisioning_started_at.isoformat() if tenant.provisioning_started_at else None
        ),
        kc_group_id=tenant.kc_group_id,
        provisioning_attempts=tenant.provisioning_attempts or 0,
    )


@router.get("/{tenant_id}/export", response_model=TenantExportResponse)
async def export_tenant(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export tenant configuration as a portable JSON archive (CAB-1474).

    Returns all tenant resources (APIs, contracts, consumers, plans,
    subscriptions, policies, skills, webhooks, MCP servers).
    Sensitive data (API keys, secrets) is excluded.

    Requires: tenant-admin (own tenant) or cpi-admin (any tenant).
    """
    # Access control: own tenant or admin
    if Role.CPI_ADMIN not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        export_service = TenantExportService(db)
        archive = await export_service.export_tenant(tenant_id)

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="export",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=user.id,
            details={"resource_counts": archive.metadata.resource_counts},
        )

        return archive

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to export tenant configuration")


@router.post("", response_model=TenantResponse)
@require_permission(Permission.TENANTS_CREATE)
async def create_tenant(
    tenant_data: TenantCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Create a new tenant (CPI Admin only).

    This will:
    1. Create tenant in database with provisioning_status=PENDING
    2. Fire async provisioning saga (KC group + admin user + policy seed + Kafka events)
    3. Return immediately — poll provisioning-status for progress
    """
    tenant_id = tenant_data.name.lower().replace(" ", "-")

    try:
        repo = TenantRepository(db)

        # Check if tenant already exists
        existing = await repo.get_by_id(tenant_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Tenant '{tenant_id}' already exists")

        # Create tenant in database with PENDING provisioning status
        tenant = Tenant(
            id=tenant_id,
            name=tenant_data.display_name,
            description=tenant_data.description,
            status=TenantStatus.ACTIVE.value,
            provisioning_status=TenantProvisioningStatus.PENDING.value,
            settings={"owner_email": tenant_data.owner_email},
        )

        tenant = await repo.create(tenant)

        # Emit Kafka event
        await kafka_service.publish(
            topic=Topics.TENANT_EVENTS,
            event_type="tenant-created",
            tenant_id=tenant_id,
            payload={
                "id": tenant_id,
                "name": tenant_data.name,
                "display_name": tenant_data.display_name,
                "owner_email": tenant_data.owner_email,
            },
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="create",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=user.id,
            details={"name": tenant_data.name},
        )

        logger.info(f"Created tenant {tenant_id} by {user.username}")

        # Fire async provisioning saga
        correlation_id = str(uuid.uuid4())
        asyncio.create_task(
            provision_tenant(
                tenant_id=tenant_id,
                owner_email=tenant_data.owner_email,
                display_name=tenant_data.display_name,
                correlation_id=correlation_id,
            )
        )

        return _tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create tenant {tenant_data.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create tenant: {e!s}")


@router.put("/{tenant_id}", response_model=TenantResponse)
@require_permission(Permission.TENANTS_UPDATE)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant in database"""
    try:
        repo = TenantRepository(db)

        # Verify tenant exists
        tenant = await repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Build update dict
        updates = {k: v for k, v in tenant_data.model_dump().items() if v is not None}

        if not updates:
            return _tenant_to_response(tenant)

        # Apply updates
        if "display_name" in updates:
            tenant.name = updates["display_name"]
        if "description" in updates:
            tenant.description = updates["description"]
        if "owner_email" in updates:
            settings = tenant.settings or {}
            settings["owner_email"] = updates["owner_email"]
            tenant.settings = settings

        tenant = await repo.update(tenant)

        # Invalidate cache
        await tenant_cache.delete(f"tenant:{tenant_id}")

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="update",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=user.id,
            details=updates,
        )

        logger.info(f"Updated tenant {tenant_id} by {user.username}")

        return _tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {e!s}")


@router.delete("/{tenant_id}")
@require_permission(Permission.TENANTS_DELETE)
async def delete_tenant(tenant_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Delete tenant (CPI Admin only).

    Triggers async deprovisioning saga: disables policies, deletes KC group,
    emits namespace cleanup event, archives tenant.
    """
    try:
        repo = TenantRepository(db)

        # Verify tenant exists
        tenant = await repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Emit audit event before deprovision
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="delete",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=user.id,
            details={"name": tenant.name},
        )

        logger.info(f"Triggering deprovisioning for tenant {tenant_id} by {user.username}")

        # Fire async deprovisioning saga
        correlation_id = str(uuid.uuid4())
        asyncio.create_task(
            deprovision_tenant(
                tenant_id=tenant_id,
                user_id=user.id,
                correlation_id=correlation_id,
            )
        )

        # Invalidate cache
        await tenant_cache.delete(f"tenant:{tenant_id}")

        return {"message": "Tenant deprovisioning started", "id": tenant_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete tenant: {e!s}")
