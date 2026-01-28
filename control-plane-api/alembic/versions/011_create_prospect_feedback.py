# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Create prospect_feedback table for NPS tracking.

Revision ID: 011
Revises: 010
Create Date: 2026-01-24

Creates table for storing NPS feedback from prospects:
- prospect_feedback: NPS scores (1-10) with optional comments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create prospect_feedback table
    op.create_table(
        'prospect_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invite_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nps_score', sa.SmallInteger(), nullable=False),
        sa.Column('comment', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invite_id', name='uq_prospect_feedback_invite_id'),
        sa.CheckConstraint('nps_score >= 1 AND nps_score <= 10', name='ck_prospect_feedback_nps_score_range'),
    )

    # Create index for NPS score analytics (promoters/passives/detractors)
    op.create_index('ix_prospect_feedback_nps_score', 'prospect_feedback', ['nps_score'])


def downgrade() -> None:
    op.drop_index('ix_prospect_feedback_nps_score', 'prospect_feedback')
    op.drop_table('prospect_feedback')
