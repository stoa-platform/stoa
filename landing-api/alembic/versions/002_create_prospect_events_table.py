"""Create prospect_events table.

Revision ID: 002
Revises: 001
Create Date: 2026-01-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create prospect_events table
    op.create_table(
        "prospect_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invite_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["invite_id"],
            ["stoa.invites.id"],
            name=op.f("fk_prospect_events_invite_id_invites"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prospect_events")),
        schema="stoa",
    )

    # Create indexes
    op.create_index(
        "idx_prospect_events_invite_timestamp",
        "prospect_events",
        ["invite_id", "timestamp"],
        schema="stoa",
    )
    op.create_index(
        "idx_prospect_events_type",
        "prospect_events",
        ["event_type"],
        schema="stoa",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_prospect_events_type",
        table_name="prospect_events",
        schema="stoa",
    )
    op.drop_index(
        "idx_prospect_events_invite_timestamp",
        table_name="prospect_events",
        schema="stoa",
    )
    op.drop_table("prospect_events", schema="stoa")
