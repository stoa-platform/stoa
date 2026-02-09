"""create consumers and plans tables, add consumer_id to subscriptions

Revision ID: 018
Revises: 017
Create Date: 2026-02-09

CAB-1121: Consumer Onboarding Phase 1 — Data Model Foundation
- consumers table: external API consumers (company, partner, developer)
- plans table: subscription plans with quota definitions
- consumer_id column on subscriptions for linking consumers
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    consumer_status_enum = sa.Enum(
        "active",
        "suspended",
        "blocked",
        name="consumer_status_enum",
    )
    plan_status_enum = sa.Enum(
        "active",
        "deprecated",
        "archived",
        name="plan_status_enum",
    )

    # Create consumers table
    op.create_table(
        "consumers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("keycloak_user_id", sa.String(255), nullable=True),
        sa.Column("status", consumer_status_enum, nullable=False, server_default="active"),
        sa.Column("consumer_metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_consumers_tenant_id", "consumers", ["tenant_id"])
    op.create_index("ix_consumers_keycloak_user_id", "consumers", ["keycloak_user_id"])
    op.create_index(
        "ix_consumers_tenant_external", "consumers", ["tenant_id", "external_id"], unique=True
    )
    op.create_index("ix_consumers_tenant_status", "consumers", ["tenant_id", "status"])
    op.create_index("ix_consumers_email", "consumers", ["email"])

    # Create plans table
    op.create_table(
        "plans",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("rate_limit_per_second", sa.Integer, nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer, nullable=True),
        sa.Column("daily_request_limit", sa.Integer, nullable=True),
        sa.Column("monthly_request_limit", sa.Integer, nullable=True),
        sa.Column("burst_limit", sa.Integer, nullable=True),
        sa.Column("requires_approval", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("auto_approve_roles", JSON, nullable=True),
        sa.Column("status", plan_status_enum, nullable=False, server_default="active"),
        sa.Column("pricing_metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_plans_tenant_id", "plans", ["tenant_id"])
    op.create_index("ix_plans_tenant_slug", "plans", ["tenant_id", "slug"], unique=True)
    op.create_index("ix_plans_tenant_status", "plans", ["tenant_id", "status"])

    # Add consumer_id to subscriptions
    op.add_column(
        "subscriptions",
        sa.Column("consumer_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_subscriptions_consumer_id", "subscriptions", ["consumer_id"])


def downgrade() -> None:
    # Drop consumer_id from subscriptions
    op.drop_index("ix_subscriptions_consumer_id", table_name="subscriptions")
    op.drop_column("subscriptions", "consumer_id")

    # Drop plans table
    op.drop_table("plans")

    # Drop consumers table
    op.drop_table("consumers")

    # Drop enums
    sa.Enum(name="plan_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="consumer_status_enum").drop(op.get_bind(), checkfirst=True)
