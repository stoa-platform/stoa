"""Tenants router - Multi-tenant management via GitOps"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..auth import get_current_user, User, Permission, require_permission, Role
from ..services.git_service import git_service
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


def _tenant_from_yaml(tenant_data: dict, api_count: int = 0, app_count: int = 0) -> TenantResponse:
    """Convert GitLab YAML data to Tenant response.

    Supports both flat format and Kubernetes-style format:
    - Flat: {name, display_name, description, ...}
    - K8s: {metadata: {name, displayName, description}, spec: {status, ...}}
    """
    # Check if this is Kubernetes-style format (has 'metadata' key)
    if "metadata" in tenant_data:
        metadata = tenant_data.get("metadata", {})
        spec = tenant_data.get("spec", {})

        name = metadata.get("name", "")
        display_name = metadata.get("displayName", metadata.get("display_name", name))
        description = metadata.get("description", "")

        # Contact info might be in spec
        contact = spec.get("contact", {})
        owner_email = contact.get("email", "")

        # Status and created_at from spec
        status = spec.get("status", "active")
        created_at = spec.get("created_at")
    else:
        # Flat format (legacy)
        name = tenant_data.get("name", "")
        display_name = tenant_data.get("display_name", name)
        description = tenant_data.get("description", "")
        owner_email = tenant_data.get("owner_email", "")
        status = tenant_data.get("status", "active")
        created_at = tenant_data.get("created_at")

    # Convert created_at to string if it's a datetime
    if created_at and not isinstance(created_at, str):
        created_at = str(created_at)

    return TenantResponse(
        id=name,
        name=name,
        display_name=display_name,
        description=description,
        owner_email=owner_email,
        status=status,
        api_count=api_count,
        application_count=app_count,
        created_at=created_at,
    )


@router.get("", response_model=List[TenantResponse])
async def list_tenants(user: User = Depends(get_current_user)):
    """
    List tenants.

    - CPI Admin: See all tenants
    - Others: See only their own tenant
    """
    try:
        # CPI Admin sees all tenants
        if Role.CPI_ADMIN in user.roles:
            # List all tenant directories from GitLab
            tenants = []
            try:
                if git_service._project:
                    tree = git_service._project.repository_tree(path="tenants", ref="main")
                    for item in tree:
                        if item["type"] == "tree":
                            try:
                                tenant_data = await git_service.get_tenant(item["name"])
                                if tenant_data:
                                    apis = await git_service.list_apis(item["name"])
                                    tenants.append(_tenant_from_yaml(tenant_data, len(apis), 0))
                            except Exception as tenant_err:
                                logger.warning(f"Failed to load tenant {item['name']}: {tenant_err}")
            except Exception as e:
                logger.error(f"Failed to list tenant directories: {e}")
            return tenants

        # Others see only their tenant
        if user.tenant_id:
            tenant_data = await git_service.get_tenant(user.tenant_id)
            if tenant_data:
                apis = await git_service.list_apis(user.tenant_id)
                return [_tenant_from_yaml(tenant_data, len(apis), 0)]

        return []

    except Exception as e:
        logger.error(f"Failed to list tenants: {e}")
        return []


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, user: User = Depends(get_current_user)):
    """Get tenant by ID"""
    # Check access
    if Role.CPI_ADMIN not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        tenant_data = await git_service.get_tenant(tenant_id)
        if not tenant_data:
            raise HTTPException(status_code=404, detail="Tenant not found")

        apis = await git_service.list_apis(tenant_id)
        return _tenant_from_yaml(tenant_data, len(apis), 0)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tenant")


@router.post("", response_model=TenantResponse)
@require_permission(Permission.TENANTS_CREATE)
async def create_tenant(tenant: TenantCreate, user: User = Depends(get_current_user)):
    """
    Create a new tenant (CPI Admin only).

    This will:
    1. Create tenant structure in GitLab
    2. Create Keycloak group for the tenant
    3. Emit tenant-created event
    """
    tenant_id = tenant.name.lower().replace(" ", "-")
    now = datetime.utcnow().isoformat() + "Z"

    tenant_data = {
        "id": tenant_id,
        "name": tenant.name,
        "display_name": tenant.display_name,
        "description": tenant.description,
        "owner_email": tenant.owner_email,
        "created_at": now,
    }

    try:
        # Create in GitLab
        await git_service.create_tenant_structure(tenant_id, tenant_data)

        # Create Keycloak group
        try:
            await keycloak_service.setup_tenant_group(tenant_id, tenant.display_name)
        except Exception as e:
            logger.warning(f"Failed to create Keycloak group for {tenant_id}: {e}")

        # Emit Kafka event
        await kafka_service.publish(
            topic=Topics.TENANT_EVENTS,
            event_type="tenant-created",
            tenant_id=tenant_id,
            payload={
                "id": tenant_id,
                "name": tenant.name,
                "display_name": tenant.display_name,
                "owner_email": tenant.owner_email,
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
            details={"name": tenant.name},
        )

        logger.info(f"Created tenant {tenant_id} by {user.username}")

        return TenantResponse(
            id=tenant_id,
            name=tenant.name,
            display_name=tenant.display_name,
            description=tenant.description,
            owner_email=tenant.owner_email,
            status="active",
            api_count=0,
            application_count=0,
            created_at=now,
        )

    except Exception as e:
        logger.error(f"Failed to create tenant {tenant.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create tenant: {str(e)}")


@router.put("/{tenant_id}", response_model=TenantResponse)
@require_permission(Permission.TENANTS_UPDATE)
async def update_tenant(
    tenant_id: str, tenant: TenantUpdate, user: User = Depends(get_current_user)
):
    """Update tenant"""
    try:
        # Verify tenant exists
        current = await git_service.get_tenant(tenant_id)
        if not current:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Build update dict
        updates = {k: v for k, v in tenant.model_dump().items() if v is not None}

        if not updates:
            apis = await git_service.list_apis(tenant_id)
            return _tenant_from_yaml(current, len(apis), 0)

        # Update current data
        current.update(updates)

        # TODO: Update in GitLab (need to implement update_tenant in git_service)

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

        apis = await git_service.list_apis(tenant_id)
        return _tenant_from_yaml(current, len(apis), 0)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update tenant: {str(e)}")


@router.delete("/{tenant_id}")
@require_permission(Permission.TENANTS_DELETE)
async def delete_tenant(tenant_id: str, user: User = Depends(get_current_user)):
    """
    Delete tenant (CPI Admin only).

    WARNING: This will delete all tenant data including APIs and applications.
    """
    try:
        # Verify tenant exists
        tenant_data = await git_service.get_tenant(tenant_id)
        if not tenant_data:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Check if tenant has APIs (safety check)
        apis = await git_service.list_apis(tenant_id)
        if apis:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete tenant with {len(apis)} APIs. Delete APIs first.",
            )

        # TODO: Delete from GitLab (implement delete_tenant in git_service)
        # TODO: Delete Keycloak group

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
            details={"name": tenant_data.get("name")},
        )

        logger.info(f"Deleted tenant {tenant_id} by {user.username}")

        return {"message": "Tenant deleted", "id": tenant_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete tenant: {str(e)}")
