"""Tenants router"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from pydantic import BaseModel

from ..auth import get_current_user, User, Permission, require_permission

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"])

class TenantCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    owner_email: str

class TenantResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    owner_email: str
    api_count: int = 0
    application_count: int = 0

@router.get("", response_model=List[TenantResponse])
async def list_tenants(user: User = Depends(get_current_user)):
    """List all tenants (CPI Admin) or own tenant (others)"""
    # TODO: Implement with GitLab service
    return []

@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, user: User = Depends(get_current_user)):
    """Get tenant by ID"""
    # TODO: Implement with GitLab service
    raise HTTPException(status_code=404, detail="Tenant not found")

@router.post("", response_model=TenantResponse)
@require_permission(Permission.TENANTS_CREATE)
async def create_tenant(tenant: TenantCreate, user: User = Depends(get_current_user)):
    """Create a new tenant (CPI Admin only)"""
    # TODO: Implement with GitLab service
    pass

@router.put("/{tenant_id}", response_model=TenantResponse)
@require_permission(Permission.TENANTS_UPDATE)
async def update_tenant(
    tenant_id: str, tenant: TenantCreate, user: User = Depends(get_current_user)
):
    """Update tenant"""
    # TODO: Implement with GitLab service
    pass

@router.delete("/{tenant_id}")
@require_permission(Permission.TENANTS_DELETE)
async def delete_tenant(tenant_id: str, user: User = Depends(get_current_user)):
    """Delete tenant (CPI Admin only)"""
    # TODO: Implement with GitLab service
    return {"message": "Tenant deleted"}
