"""APIs router"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from ..auth import get_current_user, User, Permission, require_permission, require_tenant_access

router = APIRouter(prefix="/v1/tenants/{tenant_id}/apis", tags=["APIs"])

class APICreate(BaseModel):
    name: str
    display_name: str
    version: str
    description: str = ""
    backend_url: str
    openapi_spec: Optional[str] = None

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

@router.get("", response_model=List[APIResponse])
@require_tenant_access
async def list_apis(tenant_id: str, user: User = Depends(get_current_user)):
    """List all APIs for a tenant"""
    # TODO: Implement with GitLab service
    return []

@router.get("/{api_id}", response_model=APIResponse)
@require_tenant_access
async def get_api(tenant_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Get API by ID"""
    # TODO: Implement with GitLab service
    raise HTTPException(status_code=404, detail="API not found")

@router.post("", response_model=APIResponse)
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_api(tenant_id: str, api: APICreate, user: User = Depends(get_current_user)):
    """Create a new API"""
    # TODO: Implement with GitLab service + Kafka event
    pass

@router.put("/{api_id}", response_model=APIResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def update_api(
    tenant_id: str, api_id: str, api: APICreate, user: User = Depends(get_current_user)
):
    """Update API"""
    # TODO: Implement with GitLab service + Kafka event
    pass

@router.delete("/{api_id}")
@require_permission(Permission.APIS_DELETE)
@require_tenant_access
async def delete_api(tenant_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Delete API"""
    # TODO: Implement with GitLab service + Kafka event
    return {"message": "API deleted"}
