"""add azure_apim to gateway_type_enum

Revision ID: 037
Revises: 036
Create Date: 2026-02-23

Adds the 'azure_apim' value to the existing gateway_type_enum
for Azure API Management adapter support (CAB-1428).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "037"
down_revision: str | None = "036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add azure_apim to gateway_type_enum."""
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'azure_apim'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    pass
