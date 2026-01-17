"""APIs router - API lifecycle management via GitOps"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import uuid

from ..auth import get_current_user, User, Permission, require_permission, require_tenant_access
from ..services.git_service import git_service
from ..services.kafka_service import kafka_service
from ..services.variable_resolver import variable_resolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/apis", tags=["APIs"])


class APICreate(BaseModel):
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    backend_url: str
    openapi_spec: Optional[str] = None
    tags: List[str] = []  # Tags for categorization and portal promotion


class APIUpdate(BaseModel):
    display_name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    backend_url: Optional[str] = None
    openapi_spec: Optional[str] = None
    tags: Optional[List[str]] = None  # Tags for categorization and portal promotion


class APIResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str
    version: str
    description: str
    backend_url: str
    status: str = "draft"
    deployed_dev: bool = False
    deployed_staging: bool = False
    tags: List[str] = []
    portal_promoted: bool = False  # True if API has portal:published tag


def _api_from_yaml(tenant_id: str, api_data: dict) -> APIResponse:
    """Convert GitLab YAML data to API response"""
    deployments = api_data.get("deployments", {})
    tags = api_data.get("tags", [])
    # Check if API is promoted to portal
    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
    portal_promoted = any(tag.lower() in promotion_tags for tag in tags)

    return APIResponse(
        id=api_data.get("id", api_data.get("name", "")),
        tenant_id=tenant_id,
        name=api_data.get("name", ""),
        display_name=api_data.get("display_name", api_data.get("name", "")),
        version=api_data.get("version", "1.0.0"),
        description=api_data.get("description", ""),
        backend_url=api_data.get("backend_url", ""),
        status=api_data.get("status", "draft"),
        deployed_dev=deployments.get("dev", False),
        deployed_staging=deployments.get("staging", False),
        tags=tags,
        portal_promoted=portal_promoted,
    )


@router.get("", response_model=List[APIResponse])
@require_tenant_access
async def list_apis(tenant_id: str, user: User = Depends(get_current_user)):
    """List all APIs for a tenant from GitLab"""
    try:
        apis = await git_service.list_apis(tenant_id)
        return [_api_from_yaml(tenant_id, api) for api in apis]
    except Exception as e:
        logger.error(f"Failed to list APIs for tenant {tenant_id}: {e}")
        return []


@router.get("/{api_id}", response_model=APIResponse)
@require_tenant_access
async def get_api(tenant_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Get API by ID from GitLab"""
    try:
        api_data = await git_service.get_api(tenant_id, api_id)
        if not api_data:
            raise HTTPException(status_code=404, detail="API not found")
        return _api_from_yaml(tenant_id, api_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get API {api_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve API")


@router.post("", response_model=APIResponse)
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_api(tenant_id: str, api: APICreate, user: User = Depends(get_current_user)):
    """
    Create a new API in GitLab and emit event.

    This creates the API definition in the GitOps repository:
    - tenants/{tenant_id}/apis/{api_name}/api.yaml
    - tenants/{tenant_id}/apis/{api_name}/openapi.yaml (if provided)
    """
    api_id = str(uuid.uuid4())

    # Check if portal:published tag is present for portal_promoted status
    tags = api.tags or []
    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
    portal_promoted = any(tag.lower() in promotion_tags for tag in tags)

    api_data = {
        "id": api_id,
        "name": api.name,
        "display_name": api.display_name,
        "version": api.version,
        "description": api.description,
        "backend_url": api.backend_url,
        "openapi_spec": api.openapi_spec,
        "tags": tags,
    }

    try:
        # Create in GitLab
        await git_service.create_api(tenant_id, api_data)

        # Emit Kafka event
        await kafka_service.emit_api_created(
            tenant_id=tenant_id,
            api_data={
                "id": api_id,
                "name": api.name,
                "version": api.version,
            },
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="create",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details={"name": api.name, "version": api.version},
        )

        logger.info(f"Created API {api.name} for tenant {tenant_id} by {user.username}")

        return APIResponse(
            id=api_id,
            tenant_id=tenant_id,
            name=api.name,
            display_name=api.display_name,
            version=api.version,
            description=api.description,
            backend_url=api.backend_url,
            status="draft",
            deployed_dev=False,
            deployed_staging=False,
            tags=tags,
            portal_promoted=portal_promoted,
        )

    except ValueError as e:
        # API already exists or validation error
        logger.warning(f"API creation conflict for {api.name}: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create API {api.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create API: {str(e)}")


@router.put("/{api_id}", response_model=APIResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def update_api(
    tenant_id: str, api_id: str, api: APIUpdate, user: User = Depends(get_current_user)
):
    """Update API in GitLab"""
    try:
        # Get current API
        current = await git_service.get_api(tenant_id, api_id)
        if not current:
            raise HTTPException(status_code=404, detail="API not found")

        # Build update dict (only non-None fields)
        updates = {k: v for k, v in api.model_dump().items() if v is not None}

        if not updates:
            return _api_from_yaml(tenant_id, current)

        # Update in GitLab
        await git_service.update_api(tenant_id, api_id, updates)

        # Emit Kafka event
        await kafka_service.emit_api_updated(
            tenant_id=tenant_id,
            api_data={"id": api_id, **updates},
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="update",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details=updates,
        )

        logger.info(f"Updated API {api_id} for tenant {tenant_id} by {user.username}")

        # Fetch updated API
        updated = await git_service.get_api(tenant_id, api_id)
        return _api_from_yaml(tenant_id, updated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update API: {str(e)}")


@router.delete("/{api_id}")
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_api(tenant_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Delete API from GitLab"""
    try:
        # Verify API exists
        api_data = await git_service.get_api(tenant_id, api_id)
        if not api_data:
            raise HTTPException(status_code=404, detail="API not found")

        # Delete from GitLab
        await git_service.delete_api(tenant_id, api_id)

        # Emit Kafka event
        await kafka_service.emit_api_deleted(
            tenant_id=tenant_id,
            api_id=api_id,
            user_id=user.id,
        )

        # Emit audit event
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="delete",
            resource_type="api",
            resource_id=api_id,
            user_id=user.id,
            details={"name": api_data.get("name")},
        )

        logger.info(f"Deleted API {api_id} for tenant {tenant_id} by {user.username}")

        return {"message": "API deleted", "id": api_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete API {api_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete API: {str(e)}")
