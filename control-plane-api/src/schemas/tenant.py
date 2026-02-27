"""Tenant schemas — extracted from routers/tenants.py (CAB-1315)."""

from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    owner_email: str


class TenantUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    owner_email: str | None = None
    max_apis: int | None = None
    max_applications: int | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    owner_email: str = ""
    status: str = "active"
    provisioning_status: str = "pending"
    api_count: int = 0
    application_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class TenantProvisioningStatusResponse(BaseModel):
    tenant_id: str
    provisioning_status: str
    provisioning_error: str | None = None
    provisioning_started_at: str | None = None
    kc_group_id: str | None = None
    provisioning_attempts: int = 0


class TenantUsageResponse(BaseModel):
    tenant_id: str
    api_count: int = 0
    max_apis: int = 10
    application_count: int = 0
    max_applications: int = 20


class TenantProvisionRequest(BaseModel):
    name: str
    display_name: str
    description: str = ""
    owner_email: str


class TenantProvisionResponse(BaseModel):
    tenant_id: str
    realm_name: str
    provisioning_status: str = "provisioning"
