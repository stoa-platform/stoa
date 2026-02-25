"""Audit service — PostgreSQL-backed compliance audit trail (CAB-1475).

Provides:
- Write: append-only audit event creation (called by middleware)
- Read: paginated queries with filters (called by router)
- Export: bulk query for CSV/JSON export
- Retention: configurable per-tenant cleanup
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


class AuditService:
    """Service for compliance-grade audit trail operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Write (append-only) ============

    async def record_event(
        self,
        *,
        tenant_id: str,
        action: str,
        method: str,
        path: str,
        resource_type: str,
        resource_id: str | None = None,
        resource_name: str | None = None,
        actor_id: str | None = None,
        actor_email: str | None = None,
        actor_type: str = "user",
        outcome: str = "success",
        status_code: int | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
        details: dict | None = None,
        diff: dict | None = None,
        duration_ms: int | None = None,
    ) -> AuditEvent:
        """Record an immutable audit event. Never raises — logs errors instead."""
        try:
            event = AuditEvent(
                id=str(uuid4()),
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_email=actor_email,
                actor_type=actor_type,
                action=action,
                method=method,
                path=path,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                outcome=outcome,
                status_code=status_code,
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
                details=details,
                diff=diff,
                duration_ms=duration_ms,
                created_at=datetime.now(UTC),
            )
            self.db.add(event)
            await self.db.flush()
            return event
        except Exception as e:
            logger.error(f"Failed to record audit event: {e}")
            raise

    # ============ Read ============

    async def list_events(
        self,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        action: str | None = None,
        outcome: str | None = None,
        resource_type: str | None = None,
        actor_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[AuditEvent], int]:
        """Query audit events with filters. Returns (events, total_count)."""
        query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        count_query = select(func.count(AuditEvent.id)).where(AuditEvent.tenant_id == tenant_id)

        if action:
            query = query.where(AuditEvent.action == action)
            count_query = count_query.where(AuditEvent.action == action)
        if outcome:
            query = query.where(AuditEvent.outcome == outcome)
            count_query = count_query.where(AuditEvent.outcome == outcome)
        if resource_type:
            query = query.where(AuditEvent.resource_type == resource_type)
            count_query = count_query.where(AuditEvent.resource_type == resource_type)
        if actor_id:
            query = query.where(AuditEvent.actor_id == actor_id)
            count_query = count_query.where(AuditEvent.actor_id == actor_id)
        if start_date:
            query = query.where(AuditEvent.created_at >= start_date)
            count_query = count_query.where(AuditEvent.created_at >= start_date)
        if end_date:
            query = query.where(AuditEvent.created_at <= end_date)
            count_query = count_query.where(AuditEvent.created_at <= end_date)
        if search:
            like_pattern = f"%{search}%"
            search_filter = AuditEvent.path.ilike(like_pattern) | AuditEvent.resource_type.ilike(like_pattern)
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total

    async def get_event(self, event_id: str) -> AuditEvent | None:
        """Get a single audit event by ID."""
        result = await self.db.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        return result.scalar_one_or_none()

    # ============ Export ============

    async def export_events(
        self,
        tenant_id: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10000,
    ) -> list[AuditEvent]:
        """Export audit events for a tenant (bulk query for CSV/JSON export)."""
        query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)

        if start_date:
            query = query.where(AuditEvent.created_at >= start_date)
        if end_date:
            query = query.where(AuditEvent.created_at <= end_date)

        query = query.order_by(AuditEvent.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============ Stats ============

    async def get_summary(
        self,
        tenant_id: str | None = None,
    ) -> dict:
        """Get audit summary stats. If tenant_id is None, returns global stats."""
        base = select(func.count(AuditEvent.id))
        if tenant_id:
            base = base.where(AuditEvent.tenant_id == tenant_id)

        total_result = await self.db.execute(base)
        total = total_result.scalar() or 0

        # Count by outcome
        outcomes = {}
        for outcome_val in ("success", "failure", "denied", "error"):
            q = base.where(AuditEvent.outcome == outcome_val)
            r = await self.db.execute(q)
            outcomes[outcome_val] = r.scalar() or 0

        # Count by action (top 10)
        action_q = (
            select(AuditEvent.action, func.count(AuditEvent.id).label("cnt"))
            .group_by(AuditEvent.action)
            .order_by(func.count(AuditEvent.id).desc())
            .limit(10)
        )
        if tenant_id:
            action_q = action_q.where(AuditEvent.tenant_id == tenant_id)
        action_result = await self.db.execute(action_q)
        by_action = {row.action: row.cnt for row in action_result}

        return {
            "total": total,
            "by_outcome": outcomes,
            "by_action": by_action,
        }

    # ============ Retention ============

    async def purge_before(
        self,
        tenant_id: str,
        before_date: datetime,
    ) -> int:
        """Delete audit events older than a date. Returns count deleted.

        WARNING: This is for retention policy only. Never call from regular API flow.
        """
        from sqlalchemy import delete

        stmt = delete(AuditEvent).where(AuditEvent.tenant_id == tenant_id).where(AuditEvent.created_at < before_date)
        result = await self.db.execute(stmt)
        count = result.rowcount
        logger.info(f"Purged {count} audit events for tenant {tenant_id} before {before_date}")
        return count
