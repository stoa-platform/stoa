"""Self-service tenant signup schemas (CAB-1315, CAB-1541)."""

from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field


class SignupPlan(StrEnum):
    """Available plans for self-service signup."""

    TRIAL = "trial"
    STANDARD = "standard"


class SelfServiceSignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=63, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")
    display_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    company: str | None = None
    plan: SignupPlan = SignupPlan.TRIAL
    invite_code: str | None = Field(None, max_length=64)


class SelfServiceSignupResponse(BaseModel):
    tenant_id: str
    status: str
    plan: str
    poll_url: str


class SelfServiceStatusResponse(BaseModel):
    tenant_id: str
    provisioning_status: str
    plan: str | None = None
    ready_at: str | None = None
