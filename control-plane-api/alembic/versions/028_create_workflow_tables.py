"""Create workflow tables for configurable onboarding workflows (CAB-593)

Revision ID: 028b
Revises: 028
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "028b"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workflow_templates
    op.create_table(
        "workflow_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("workflow_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(50), nullable=False, server_default="auto"),
        sa.Column("approval_steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("auto_provision", sa.String(5), nullable=False, server_default="true"),
        sa.Column("notification_config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sector", sa.String(50), nullable=True),
        sa.Column("is_active", sa.String(5), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_wf_templates_tenant_id", "workflow_templates", ["tenant_id"])
    op.create_index("ix_wf_templates_tenant_type", "workflow_templates", ["tenant_id", "workflow_type"])
    op.create_index("ix_wf_templates_tenant_active", "workflow_templates", ["tenant_id", "is_active"])

    # workflow_instances
    op.create_table(
        "workflow_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("workflow_type", sa.String(50), nullable=False),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("subject_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("initiated_by", sa.String(255), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wf_instances_tenant_id", "workflow_instances", ["tenant_id"])
    op.create_index("ix_wf_instances_template", "workflow_instances", ["template_id"])
    op.create_index("ix_wf_instances_tenant_status", "workflow_instances", ["tenant_id", "status"])
    op.create_index("ix_wf_instances_tenant_type", "workflow_instances", ["tenant_id", "workflow_type"])
    op.create_index("ix_wf_instances_tenant_created", "workflow_instances", ["tenant_id", "created_at"])

    # workflow_step_results
    op.create_table(
        "workflow_step_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wf_steps_instance_id", "workflow_step_results", ["instance_id"])
    op.create_index("ix_wf_steps_instance_index", "workflow_step_results", ["instance_id", "step_index"])

    # workflow_audit_logs
    op.create_table(
        "workflow_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wf_audit_instance_id", "workflow_audit_logs", ["instance_id"])
    op.create_index("ix_wf_audit_instance_created", "workflow_audit_logs", ["instance_id", "created_at"])
    op.create_index("ix_wf_audit_event_type", "workflow_audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_wf_audit_event_type", table_name="workflow_audit_logs")
    op.drop_index("ix_wf_audit_instance_created", table_name="workflow_audit_logs")
    op.drop_index("ix_wf_audit_instance_id", table_name="workflow_audit_logs")
    op.drop_table("workflow_audit_logs")

    op.drop_index("ix_wf_steps_instance_index", table_name="workflow_step_results")
    op.drop_index("ix_wf_steps_instance_id", table_name="workflow_step_results")
    op.drop_table("workflow_step_results")

    op.drop_index("ix_wf_instances_tenant_created", table_name="workflow_instances")
    op.drop_index("ix_wf_instances_tenant_type", table_name="workflow_instances")
    op.drop_index("ix_wf_instances_tenant_status", table_name="workflow_instances")
    op.drop_index("ix_wf_instances_template", table_name="workflow_instances")
    op.drop_index("ix_wf_instances_tenant_id", table_name="workflow_instances")
    op.drop_table("workflow_instances")

    op.drop_index("ix_wf_templates_tenant_active", table_name="workflow_templates")
    op.drop_index("ix_wf_templates_tenant_type", table_name="workflow_templates")
    op.drop_index("ix_wf_templates_tenant_id", table_name="workflow_templates")
    op.drop_table("workflow_templates")
