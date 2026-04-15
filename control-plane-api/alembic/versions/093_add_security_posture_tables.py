"""add security_findings, security_scans, security_baselines tables

Revision ID: 093
Revises: 091_add_is_platform_and_seed_gateway
Create Date: 2026-04-08

CAB-2008: tables for Security Posture dashboard — scanner findings,
scan history, and golden state drift detection.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "093_add_security_posture_tables"
down_revision = "091_add_is_platform_and_seed_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("scanner", sa.String(50), nullable=False),
        sa.Column("scan_type", sa.String(50), nullable=False, server_default="trivy"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("findings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("scan_duration_ms", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "security_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("scan_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("scanner", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("rule_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_name", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("remediation", sa.Text, nullable=True),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("now()"), index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "security_baselines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, unique=True),
        sa.Column("baseline", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("security_baselines")
    op.drop_table("security_findings")
    op.drop_table("security_scans")
