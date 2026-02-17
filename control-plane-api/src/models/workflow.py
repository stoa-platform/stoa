"""Workflow SQLAlchemy models for configurable onboarding workflows (CAB-593)"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


class WorkflowType(enum.StrEnum):
    """Types of onboarding workflows"""

    USER_REGISTRATION = "user_registration"
    CONSUMER_REGISTRATION = "consumer_registration"
    TENANT_OWNER = "tenant_owner"


class WorkflowMode(enum.StrEnum):
    """Workflow approval modes"""

    AUTO = "auto"
    MANUAL = "manual"
    APPROVAL_CHAIN = "approval_chain"


class WorkflowStatus(enum.StrEnum):
    """Workflow instance status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    FAILED = "failed"


class Sector(enum.StrEnum):
    """Industry sector presets"""

    FINTECH = "fintech"
    STARTUP = "startup"
    ENTERPRISE = "enterprise"


class StepAction(enum.StrEnum):
    """Approval step actions"""

    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class WorkflowTemplate(Base):
    """Workflow template — per tenant, per workflow_type"""

    __tablename__ = "workflow_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    workflow_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    mode = Column(String(50), nullable=False, default=WorkflowMode.AUTO.value)
    approval_steps = Column(JSONB, nullable=False, server_default="[]")
    auto_provision = Column(String(5), nullable=False, server_default="true")
    notification_config = Column(JSONB, nullable=False, server_default="{}")
    sector = Column(String(50), nullable=True)
    is_active = Column(String(5), nullable=False, server_default="true")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_wf_templates_tenant_type", "tenant_id", "workflow_type"),
        Index("ix_wf_templates_tenant_active", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowTemplate {self.id} tenant={self.tenant_id} type={self.workflow_type} mode={self.mode}>"


class WorkflowInstance(Base):
    """Workflow instance — one per onboarding request"""

    __tablename__ = "workflow_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    workflow_type = Column(String(50), nullable=False)
    subject_id = Column(String(255), nullable=False)
    subject_email = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default=WorkflowStatus.PENDING.value)
    current_step_index = Column(Integer, nullable=False, default=0)
    context = Column(JSONB, nullable=False, server_default="{}")
    initiated_by = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_wf_instances_tenant_status", "tenant_id", "status"),
        Index("ix_wf_instances_template", "template_id"),
        Index("ix_wf_instances_tenant_type", "tenant_id", "workflow_type"),
        Index("ix_wf_instances_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowInstance {self.id} status={self.status} step={self.current_step_index}>"


class WorkflowStepResult(Base):
    """Workflow step result — one per approval step per instance"""

    __tablename__ = "workflow_step_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    approver_id = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_wf_steps_instance_index", "instance_id", "step_index"),)

    def __repr__(self) -> str:
        return f"<WorkflowStepResult {self.id} instance={self.instance_id} step={self.step_index} action={self.action}>"


class WorkflowAuditLog(Base):
    """Workflow audit log — immutable, append-only"""

    __tablename__ = "workflow_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    actor_id = Column(String(255), nullable=True)
    details = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_wf_audit_instance_created", "instance_id", "created_at"),
        Index("ix_wf_audit_event_type", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowAuditLog {self.id} instance={self.instance_id} event={self.event_type}>"
