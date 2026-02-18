"""Skill repository — CRUD + CSS cascade resolution (CAB-1314)."""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.skill import Skill, SkillScope

# CSS specificity: higher value = higher specificity
SCOPE_SPECIFICITY: dict[SkillScope, int] = {
    SkillScope.GLOBAL: 0,
    SkillScope.TENANT: 1,
    SkillScope.TOOL: 2,
    SkillScope.USER: 3,
}


class SkillRepository:
    """Data access layer for skills."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, tenant_id: str, **kwargs: object) -> Skill:
        skill = Skill(tenant_id=tenant_id, **kwargs)
        self.session.add(skill)
        await self.session.flush()
        return skill

    async def get(self, skill_id: UUID) -> Skill | None:
        return await self.session.get(Skill, skill_id)

    async def list_by_tenant(
        self,
        tenant_id: str,
        scope: SkillScope | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Skill]:
        stmt = select(Skill).where(Skill.tenant_id == tenant_id)
        if scope is not None:
            stmt = stmt.where(Skill.scope == scope)
        stmt = stmt.order_by(Skill.name).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_tenant(
        self,
        tenant_id: str,
        scope: SkillScope | None = None,
    ) -> int:
        stmt = select(func.count(Skill.id)).where(Skill.tenant_id == tenant_id)
        if scope is not None:
            stmt = stmt.where(Skill.scope == scope)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update(self, skill_id: UUID, **kwargs: object) -> Skill | None:
        # Filter out None values for partial update
        values = {k: v for k, v in kwargs.items() if v is not None}
        if not values:
            return await self.get(skill_id)
        stmt = update(Skill).where(Skill.id == skill_id).values(**values).returning(Skill)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, skill_id: UUID) -> bool:
        stmt = delete(Skill).where(Skill.id == skill_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def list_resolved(
        self,
        tenant_id: str,
        tool_ref: str | None = None,
        user_ref: str | None = None,
    ) -> list[dict]:
        """Resolve skills using CSS cascade: filter by scope, sort by specificity desc + priority desc."""
        stmt = select(Skill).where(
            Skill.tenant_id == tenant_id,
            Skill.enabled.is_(True),
        )

        # Include skills matching the context
        scope_filters = [SkillScope.GLOBAL, SkillScope.TENANT]
        if tool_ref:
            scope_filters.append(SkillScope.TOOL)
        if user_ref:
            scope_filters.append(SkillScope.USER)

        stmt = stmt.where(Skill.scope.in_(scope_filters))
        result = await self.session.execute(stmt)
        skills = list(result.scalars().all())

        # Further filter: tool-scoped skills must match tool_ref, user-scoped must match user_ref
        filtered = []
        for skill in skills:
            if skill.scope == SkillScope.TOOL and skill.tool_ref != tool_ref:
                continue
            if skill.scope == SkillScope.USER and skill.user_ref != user_ref:
                continue
            filtered.append(skill)

        # Sort by specificity desc, then priority desc (CSS cascade)
        filtered.sort(
            key=lambda s: (SCOPE_SPECIFICITY.get(s.scope, 0), s.priority),
            reverse=True,
        )

        return [
            {
                "name": s.name,
                "scope": s.scope,
                "priority": s.priority,
                "instructions": s.instructions,
                "specificity": SCOPE_SPECIFICITY.get(s.scope, 0),
            }
            for s in filtered
        ]
