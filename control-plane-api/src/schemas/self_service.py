"""Self-service tenant signup schemas (CAB-1315)."""

from pydantic import BaseModel, EmailStr


class SelfServiceSignupRequest(BaseModel):
    name: str
    display_name: str
    owner_email: EmailStr
    company: str | None = None


class SelfServiceSignupResponse(BaseModel):
    tenant_id: str
    status: str
    poll_url: str


class SelfServiceStatusResponse(BaseModel):
    tenant_id: str
    provisioning_status: str
    ready_at: str | None = None
