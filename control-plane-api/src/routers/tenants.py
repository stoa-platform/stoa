# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tenants router - Multi-tenant management using database"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..auth import get_current_user, User, Permission, require_permission, Role
from ..database import get_db
from ..models.tenant import Tenant, TenantStatus
from ..repositories.tenant import TenantRepository
from ..services.kafka_service import kafka_service, Topics
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"])


class TenantCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    owner_email: str


class TenantUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    owner_email: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    owner_email: str = ""
    status: str = "active"
    api_count: int = 0
    application_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


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
        api_count=api_count,
        application_count=app_count,
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
    )


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List tenants from database.

    - CPI Admin: See all tenants
    - Others: See only their own tenant
    """
    try:
        repo = TenantRepository(db)
        is_admin = Role.CPI_ADMIN in user.roles

        tenants = await repo.list_for_user(
            tenant_id=user.tenant_id,
            is_admin=is_admin
        )

        return [_tenant_to_response(t) for t in tenants]

    except Exception as e:
        logger.error(f"Failed to list tenants: {e}")
        return []


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tenant by ID from database"""
    # Check access
    if Role.CPI_ADMIN not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        repo = TenantRepository(db)
        tenant = await repo.get_by_id(tenant_id)

        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        return _tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tenant")


@router.post("", response_model=TenantResponse)
@require_permission(Permission.TENANTS_CREATE)
async def create_tenant(
    tenant_data: TenantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new tenant (CPI Admin only).

    This will:
    1. Create tenant in database
    2. Create Keycloak group for the tenant
    3. Emit tenant-created event
    """
    tenant_id = tenant_data.name.lower().replace(" ", "-")

    try:
        repo = TenantRepository(db)

        # Check if tenant already exists
        existing = await repo.get_by_id(tenant_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Tenant '{tenant_id}' already exists")

        # Create tenant in database
        tenant = Tenant(
            id=tenant_id,
            name=tenant_data.display_name,
            description=tenant_data.description,
            status=TenantStatus.ACTIVE.value,
            settings={"owner_email": tenant_data.owner_email},
        )

        tenant = await repo.create(tenant)

        # Create Keycloak group
        try:
            await keycloak_service.setup_tenant_group(tenant_id, tenant_data.display_name)
        except Exception as e:
            logger.warning(f"Failed to create Keycloak group for {tenant_id}: {e}")

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

        return _tenant_to_response(tenant)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create tenant {tenant_data.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create tenant: {str(e)}")


@router.put("/{tenant_id}", response_model=TenantResponse)
@require_permission(Permission.TENANTS_UPDATE)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {str(e)}")


@router.delete("/{tenant_id}")
@require_permission(Permission.TENANTS_DELETE)
async def delete_tenant(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete tenant (CPI Admin only).

    WARNING: This will archive the tenant (soft delete).
    """
    try:
        repo = TenantRepository(db)

        # Verify tenant exists
        tenant = await repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Soft delete - set status to archived
        tenant.status = TenantStatus.ARCHIVED.value
        await repo.update(tenant)

        # Emit Kafka event
        await kafka_service.publish(
            topic=Topics.TENANT_EVENTS,
            event_type="tenant-deleted",
            tenant_id=tenant_id,
            payload={"id": tenant_id},
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="delete",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=user.id,
            details={"name": tenant.name},
        )

        logger.info(f"Archived tenant {tenant_id} by {user.username}")

        return {"message": "Tenant archived", "id": tenant_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete tenant: {str(e)}")
