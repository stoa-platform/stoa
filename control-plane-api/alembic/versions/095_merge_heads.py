"""merge heads 092 (drop execution_logs) and 094 (seed gateway_deployments)

Revision ID: 095_merge_heads
Revises: 092, 094_seed_gateway_deployments
Create Date: 2026-04-16

Two migration chains both branched off 091_add_is_platform_and_seed_gateway:

- 091 -> 092                                        (CAB-1977, drop execution_logs)
- 091 -> 093_add_security_posture_tables -> 094_seed_gateway_deployments  (CAB-2008 + CAB-2034)

They merged to main independently, leaving alembic with two heads and
blocking `alembic upgrade head` in prod (prod stuck at 090). This no-op
migration reconciles the heads so future upgrades can proceed linearly.

No schema change; pure lineage merge.
"""

revision = "095_merge_heads"
down_revision = ("092", "094_seed_gateway_deployments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
