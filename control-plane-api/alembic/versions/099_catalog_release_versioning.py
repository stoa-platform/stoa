"""catalog release versioning metadata

Revision ID: 099_catalog_release_versioning
Revises: 098_gateway_topology_norm
Create Date: 2026-05-01

Stores the GitOps release object attached to an accepted catalog desired-state
generation. This makes PR, merge commit and release tag visible to CP/API/UI
without changing the canonical catalog file shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "099_catalog_release_versioning"
down_revision: str | tuple[str, ...] | None = "098_gateway_topology_norm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_catalog", sa.Column("catalog_release_id", sa.String(length=80), nullable=True))
    op.add_column("api_catalog", sa.Column("catalog_release_tag", sa.String(length=255), nullable=True))
    op.add_column("api_catalog", sa.Column("catalog_pr_url", sa.String(length=500), nullable=True))
    op.add_column("api_catalog", sa.Column("catalog_pr_number", sa.Integer(), nullable=True))
    op.add_column("api_catalog", sa.Column("catalog_source_branch", sa.String(length=255), nullable=True))
    op.add_column("api_catalog", sa.Column("catalog_merge_commit_sha", sa.String(length=40), nullable=True))

    op.create_index("ix_api_catalog_release_tag", "api_catalog", ["catalog_release_tag"])
    op.create_index("ix_api_catalog_merge_commit", "api_catalog", ["catalog_merge_commit_sha"])


def downgrade() -> None:
    op.drop_index("ix_api_catalog_merge_commit", table_name="api_catalog")
    op.drop_index("ix_api_catalog_release_tag", table_name="api_catalog")

    op.drop_column("api_catalog", "catalog_merge_commit_sha")
    op.drop_column("api_catalog", "catalog_source_branch")
    op.drop_column("api_catalog", "catalog_pr_number")
    op.drop_column("api_catalog", "catalog_pr_url")
    op.drop_column("api_catalog", "catalog_release_tag")
    op.drop_column("api_catalog", "catalog_release_id")
