"""Add oauth_client_id to subscriptions, make api_key columns nullable.

Subscription Architecture Overhaul — Phase 1: Remove API key generation,
use OAuth2 client_credentials flow via Keycloak client_id.

Revision ID: 056_subscription_oauth
Revises: 055_add_environment_column
Create Date: 2026-03-05
"""

import sqlalchemy as sa
from alembic import op

revision = "056_subscription_oauth"
down_revision = "055_add_environment_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add oauth_client_id column (from PortalApplication.keycloak_client_id)
    op.add_column("subscriptions", sa.Column("oauth_client_id", sa.String(255), nullable=True))

    # Make api_key columns nullable (backward compatible — existing keys keep working)
    op.alter_column("subscriptions", "api_key_hash", existing_type=sa.String(512), nullable=True)
    op.alter_column("subscriptions", "api_key_prefix", existing_type=sa.String(20), nullable=True)

    # Drop the old unique constraint on api_key_hash (nullable columns + unique is problematic)
    op.drop_constraint("subscriptions_api_key_hash_key", "subscriptions", type_="unique")

    # Composite index for gateway validation lookups (oauth_client_id + api_id)
    op.create_index("ix_subscriptions_oauth_client_api", "subscriptions", ["oauth_client_id", "api_id"])

    # Partial unique constraint: prevent duplicate active/pending subscriptions for same client+api
    op.execute(
        "CREATE UNIQUE INDEX ix_subscriptions_oauth_client_api_active "
        "ON subscriptions (oauth_client_id, api_id) "
        "WHERE status IN ('pending', 'active') AND oauth_client_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_oauth_client_api_active")
    op.drop_index("ix_subscriptions_oauth_client_api", table_name="subscriptions")

    # Restore api_key columns to NOT NULL (will fail if NULL values exist)
    op.alter_column("subscriptions", "api_key_prefix", existing_type=sa.String(20), nullable=False)
    op.alter_column("subscriptions", "api_key_hash", existing_type=sa.String(512), nullable=False)

    # Restore unique constraint on api_key_hash
    op.create_unique_constraint("subscriptions_api_key_hash_key", "subscriptions", ["api_key_hash"])

    op.drop_column("subscriptions", "oauth_client_id")
