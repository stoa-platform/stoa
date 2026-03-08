"""add security_profile to portal_applications

Revision ID: 059
Revises: 058
Create Date: 2026-03-06

CAB-1744: Security Profile per Application — curated auth combinations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "059"
down_revision: str | None = "058_create_proxy_backends"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the enum type
    security_profile_enum = sa.Enum(
        "api_key",
        "oauth2_public",
        "oauth2_confidential",
        "fapi_baseline",
        "fapi_advanced",
        name="security_profile_enum",
    )
    security_profile_enum.create(op.get_bind(), checkfirst=True)

    # Add security_profile column with default for existing rows
    op.add_column(
        "portal_applications",
        sa.Column(
            "security_profile",
            security_profile_enum,
            nullable=False,
            server_default="oauth2_public",
        ),
    )

    # Add api_key_hash column (for api_key profile)
    op.add_column(
        "portal_applications",
        sa.Column("api_key_hash", sa.String(64), nullable=True),
    )

    # Add api_key_prefix column (for display)
    op.add_column(
        "portal_applications",
        sa.Column("api_key_prefix", sa.String(12), nullable=True),
    )

    # Add jwks_uri column (for fapi profiles with private_key_jwt)
    op.add_column(
        "portal_applications",
        sa.Column("jwks_uri", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portal_applications", "jwks_uri")
    op.drop_column("portal_applications", "api_key_prefix")
    op.drop_column("portal_applications", "api_key_hash")
    op.drop_column("portal_applications", "security_profile")

    sa.Enum(name="security_profile_enum").drop(op.get_bind(), checkfirst=True)
