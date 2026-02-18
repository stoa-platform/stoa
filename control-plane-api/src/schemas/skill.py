"""Skill schemas — Pydantic v2 request/response models (CAB-1314)."""

from uuid import UUID

from pydantic import BaseModel, Field

from ..models.skill import SkillScope


class SkillCreate(BaseModel):
    """Create a new skill."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    scope: SkillScope = SkillScope.TENANT
    priority: int = Field(default=50, ge=0, le=100)
    instructions: str | None = None
    tool_ref: str | None = None
    user_ref: str | None = None
    enabled: bool = True


class SkillUpdate(BaseModel):
    """Partial update a skill."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scope: SkillScope | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    instructions: str | None = None
    tool_ref: str | None = None
    user_ref: str | None = None
    enabled: bool | None = None


class SkillResponse(BaseModel):
    """Skill response."""

    id: UUID
    tenant_id: str
    name: str
    description: str | None = None
    scope: SkillScope
    priority: int
    instructions: str | None = None
    tool_ref: str | None = None
    user_ref: str | None = None
    enabled: bool

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    """Paginated skill list."""

    items: list[SkillResponse]
    total: int


class ResolvedSkillResponse(BaseModel):
    """A skill after CSS cascade resolution — includes computed specificity."""

    name: str
    scope: SkillScope
    priority: int
    instructions: str | None = None
    specificity: int
