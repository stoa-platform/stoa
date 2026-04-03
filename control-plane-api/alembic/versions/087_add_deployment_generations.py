"""Add generation columns for K8s-style reconciliation (CAB-1950).

Revision ID: 087_add_deployment_generations
Revises: 086_add_sync_steps
"""

from alembic import op
import sqlalchemy as sa

revision = "087_add_deployment_generations"
down_revision = "086_add_sync_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_deployments",
        sa.Column("desired_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "gateway_deployments",
        sa.Column("synced_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "gateway_deployments",
        sa.Column("attempted_generation", sa.Integer(), nullable=False, server_default="0"),
    )

    # Initialize existing deployments based on current sync_status:
    # - synced: all generations = 1 (already reconciled)
    # - error: desired=1, attempted=1, synced=0 (attempted but failed — don't retry)
    # - pending/drifted: desired=1, attempted=0, synced=0 (needs sync)
    op.execute(
        "UPDATE gateway_deployments SET desired_generation=1, synced_generation=1, attempted_generation=1 "
        "WHERE sync_status = 'synced'"
    )
    op.execute(
        "UPDATE gateway_deployments SET desired_generation=1, synced_generation=0, attempted_generation=1 "
        "WHERE sync_status = 'error'"
    )
    op.execute(
        "UPDATE gateway_deployments SET desired_generation=1, synced_generation=0, attempted_generation=0 "
        "WHERE sync_status IN ('pending', 'drifted', 'syncing', 'deleting')"
    )


def downgrade() -> None:
    op.drop_column("gateway_deployments", "attempted_generation")
    op.drop_column("gateway_deployments", "synced_generation")
    op.drop_column("gateway_deployments", "desired_generation")
