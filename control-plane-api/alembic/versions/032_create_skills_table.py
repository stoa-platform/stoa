"""Create skills table for CSS cascade context injection (CAB-1314)

Revision ID: 032
Revises: 031
Create Date: 2026-02-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type first
    skill_scope_enum = sa.Enum("global", "tenant", "tool", "user", name="skill_scope_enum", create_type=True)
    skill_scope_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scope", skill_scope_enum, nullable=False, server_default="tenant"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="50"),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("tool_ref", sa.String(255), nullable=True),
        sa.Column("user_ref", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )

    op.create_index("ix_skills_tenant_id", "skills", ["tenant_id"])
    op.create_index("ix_skills_tenant_scope", "skills", ["tenant_id", "scope"])
    op.create_index("ix_skills_tenant_name", "skills", ["tenant_id", "name"])
    op.create_index(
        "ix_skills_tenant_name_scope",
        "skills",
        ["tenant_id", "name", "scope"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skills_tenant_name_scope", table_name="skills")
    op.drop_index("ix_skills_tenant_name", table_name="skills")
    op.drop_index("ix_skills_tenant_scope", table_name="skills")
    op.drop_index("ix_skills_tenant_id", table_name="skills")
    op.drop_table("skills")
    sa.Enum(name="skill_scope_enum").drop(op.get_bind(), checkfirst=True)
