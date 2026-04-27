"""add catalog_content_hash to api_catalog

Revision ID: 097_add_catalog_content_hash
Revises: 096_fix_subscription_demo_column_types
Create Date: 2026-04-27

Spec ref: ``specs/api-creation-gitops-rewrite.md`` §6.3, §6.6
(CAB-2180 B-CATALOG, CAB-2182 B-HASH).

Out-of-scope:
* any modification to ``git_path`` or ``git_commit_sha`` (already exist)
* ``uq_api_catalog_tenant_api`` cleanup (CAB-2192 B-INDEX deferred)
* backfill of existing rows (cycle séparé pour cat D, see spec §11)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "097_add_catalog_content_hash"
down_revision: str | tuple[str, ...] | None = "096_fix_subscription_demo_column_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_catalog",
        sa.Column("catalog_content_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_catalog", "catalog_content_hash")
