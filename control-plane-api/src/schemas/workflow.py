"""Pydantic schemas for workflow engine API (CAB-593)"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovalStepDef(BaseModel):
    """Definition of a single approval step in a chain"""

    step_index: int = Field(..., ge=0)
    role: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=255)


class TemplateCreate(BaseModel):
    """Create a workflow template"""

    workflow_type: str = Field(..., pattern="^(user_registration|consumer_registration|tenant_owner)$")
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    mode: str = Field(default="auto", pattern="^(auto|manual|approval_chain)$")
    approval_steps: list[ApprovalStepDef] = Field(default_factory=list)
    auto_provision: bool = True
    notification_config: dict = Field(default_factory=dict)
    sector: str | None = Field(default=None, pattern="^(fintech|startup|enterprise)$")

    @model_validator(mode="after")
    def validate_steps_for_mode(self) -> "TemplateCreate":
        if self.mode == "approval_chain" and not self.approval_steps:
            raise ValueError("approval_chain mode requires at least one approval step")
        if self.mode == "auto" and self.approval_steps:
            raise ValueError("auto mode must not have approval steps")
        return self


class TemplateUpdate(BaseModel):
    """Update a workflow template"""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    mode: str | None = Field(default=None, pattern="^(auto|manual|approval_chain)$")
    approval_steps: list[ApprovalStepDef] | None = None
    auto_provision: bool | None = None
    notification_config: dict | None = None
    sector: str | None = Field(default=None, pattern="^(fintech|startup|enterprise)$")
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    """Workflow template response"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    workflow_type: str
    name: str
    description: str | None = None
    mode: str
    approval_steps: list | None = Field(default_factory=list)
    auto_provision: str
    notification_config: dict | None = Field(default_factory=dict)
    sector: str | None = None
    is_active: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None


class TemplateListResponse(BaseModel):
    """Paginated template list"""

    items: list[TemplateResponse]
    total: int
    page: int = 1
    page_size: int = 50


class InstanceCreate(BaseModel):
    """Start a new workflow instance"""

    template_id: UUID
    subject_id: str = Field(..., min_length=1, max_length=255)
    subject_email: str | None = Field(default=None, max_length=255)
    context: dict = Field(default_factory=dict)


class InstanceResponse(BaseModel):
    """Workflow instance response"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    tenant_id: str
    workflow_type: str
    subject_id: str
    subject_email: str | None = None
    status: str
    current_step_index: int
    context: dict | None = Field(default_factory=dict)
    initiated_by: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InstanceListResponse(BaseModel):
    """Paginated instance list"""

    items: list[InstanceResponse]
    total: int
    page: int = 1
    page_size: int = 50


class StepActionRequest(BaseModel):
    """Approve or reject a workflow step"""

    comment: str | None = Field(default=None, max_length=1000)


class StepResultResponse(BaseModel):
    """Step result response"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instance_id: UUID
    step_index: int
    approver_id: str
    action: str
    comment: str | None = None
    created_at: datetime


class AuditResponse(BaseModel):
    """Workflow audit log entry"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instance_id: UUID
    event_type: str
    actor_id: str | None = None
    details: dict | None = Field(default_factory=dict)
    created_at: datetime


class AuditListResponse(BaseModel):
    """Paginated audit list"""

    items: list[AuditResponse]
    total: int
    page: int = 1
    page_size: int = 50
