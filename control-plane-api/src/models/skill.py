"""Skill model — CSS cascade context injection for AI agents (CAB-1314)."""

import enum
import uuid

from sqlalchemy import Boolean, Column, Enum as SAEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class SkillScope(enum.StrEnum):
    """Skill specificity scope — higher specificity wins (CSS cascade model)."""

    GLOBAL = "global"  # specificity 0
    TENANT = "tenant"  # specificity 1
    TOOL = "tool"  # specificity 2
    USER = "user"  # specificity 3


class Skill(Base):
    """Skill — contextual instructions injected into AI agent sessions."""

    __tablename__ = "skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scope = Column(
        SAEnum(SkillScope, name="skill_scope_enum", create_constraint=True),
        nullable=False,
        default=SkillScope.TENANT,
    )
    priority = Column(Integer, nullable=False, default=50)
    instructions = Column(Text, nullable=True)
    tool_ref = Column(String(255), nullable=True)
    user_ref = Column(String(255), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_skills_tenant_scope", "tenant_id", "scope"),
        Index("ix_skills_tenant_name", "tenant_id", "name"),
        Index("ix_skills_tenant_name_scope", "tenant_id", "name", "scope", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Skill name={self.name!r} scope={self.scope!r} priority={self.priority}>"
