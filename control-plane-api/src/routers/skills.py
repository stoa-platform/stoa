"""Skills router — CRUD + CSS cascade resolution (CAB-1314)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.skill import SkillScope
from ..repositories.skill import SkillRepository
from ..schemas.skill import (
    ResolvedSkillResponse,
    SkillCreate,
    SkillListResponse,
    SkillResponse,
    SkillUpdate,
)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/skills", tags=["Skills"])


def _repo(db: AsyncSession = Depends(get_db)) -> SkillRepository:
    return SkillRepository(db)


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    tenant_id: str,
    body: SkillCreate,
    repo: SkillRepository = Depends(_repo),
) -> SkillResponse:
    """Create a new skill for a tenant."""
    skill = await repo.create(tenant_id=tenant_id, **body.model_dump())
    return SkillResponse.model_validate(skill)


@router.get("", response_model=SkillListResponse)
async def list_skills(
    tenant_id: str,
    scope: SkillScope | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    repo: SkillRepository = Depends(_repo),
) -> SkillListResponse:
    """List skills for a tenant, optionally filtered by scope."""
    items = await repo.list_by_tenant(tenant_id, scope=scope, limit=limit, offset=offset)
    total = await repo.count_by_tenant(tenant_id, scope=scope)
    return SkillListResponse(
        items=[SkillResponse.model_validate(s) for s in items],
        total=total,
    )


@router.get("/resolve", response_model=list[ResolvedSkillResponse])
async def resolve_skills(
    tenant_id: str,
    tool_ref: str | None = None,
    user_ref: str | None = None,
    repo: SkillRepository = Depends(_repo),
) -> list[ResolvedSkillResponse]:
    """Resolve skills using CSS cascade: global < tenant < tool < user."""
    resolved = await repo.list_resolved(tenant_id, tool_ref=tool_ref, user_ref=user_ref)
    return [ResolvedSkillResponse(**r) for r in resolved]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    tenant_id: str,
    skill_id: UUID,
    repo: SkillRepository = Depends(_repo),
) -> SkillResponse:
    """Get a skill by ID."""
    skill = await repo.get(skill_id)
    if not skill or skill.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse.model_validate(skill)


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    tenant_id: str,
    skill_id: UUID,
    body: SkillUpdate,
    repo: SkillRepository = Depends(_repo),
) -> SkillResponse:
    """Partially update a skill."""
    existing = await repo.get(skill_id)
    if not existing or existing.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    updated = await repo.update(skill_id, **body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse.model_validate(updated)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    tenant_id: str,
    skill_id: UUID,
    repo: SkillRepository = Depends(_repo),
) -> None:
    """Delete a skill."""
    existing = await repo.get(skill_id)
    if not existing or existing.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    await repo.delete(skill_id)
