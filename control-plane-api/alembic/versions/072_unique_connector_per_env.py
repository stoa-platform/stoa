"""Add unique constraint on (connector_template_id, tenant_id, environment).

Ensures a connector can only be connected once per tenant per environment,
enabling multi-environment deployment (dev → staging → production).

Revision ID: 072_unique_connector_per_env
Revises: 071_add_dcr_connectors
"""

from alembic import op

revision = "072_unique_connector_per_env"
down_revision = "071_add_dcr_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_external_mcp_servers_template_tenant_env",
        "external_mcp_servers",
        ["connector_template_id", "tenant_id", "environment"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_external_mcp_servers_template_tenant_env",
        "external_mcp_servers",
        type_="unique",
    )
