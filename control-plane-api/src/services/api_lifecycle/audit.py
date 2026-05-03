"""Audit adapter for API lifecycle transitions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_event import AuditEvent

from .ports import LifecycleActor


class SqlAlchemyLifecycleAuditSink:
    """Writes lifecycle transitions to the existing immutable audit table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_transition(
        self,
        *,
        tenant_id: str,
        actor: LifecycleActor,
        action: str,
        resource_id: str,
        resource_name: str,
        details: dict[str, Any],
        outcome: str = "success",
        status_code: int = 200,
        method: str = "POST",
        path: str | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_id=actor.actor_id,
                actor_email=actor.email,
                actor_type=actor.actor_type,
                action=action,
                method=method,
                path=path or f"/v1/tenants/{tenant_id}/apis/lifecycle/drafts",
                resource_type="api",
                resource_id=resource_id,
                resource_name=resource_name,
                outcome=outcome,
                status_code=status_code,
                details=details,
            )
        )
        await self.session.flush()
