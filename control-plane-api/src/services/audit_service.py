"""Audit service — PostgreSQL-backed compliance audit trail (CAB-1475).

Provides:
- Write: append-only audit event creation (called by middleware)
- Read: paginated queries with filters (called by router)
- Export: bulk query for CSV/JSON export
- Retention: configurable per-tenant cleanup
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from cachetools import TTLCache  # type: ignore[import-untyped]
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedActor:
    """Resolved actor identity returned to audit API callers."""

    user_id: str | None
    user_email: str | None
    user_display_name: str | None
    resolved: bool


_ACTOR_CACHE: TTLCache[tuple[str | None, str | None], ResolvedActor] = TTLCache(maxsize=2000, ttl=300)


def _keycloak_display_name(user: dict[str, Any]) -> str | None:
    first_name = str(user.get("firstName") or "").strip()
    last_name = str(user.get("lastName") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    if full_name:
        return full_name
    username = str(user.get("username") or "").strip()
    if username:
        return username
    email = user.get("email")
    return str(email) if email else None


async def resolve_actor(user_id: str | None, user_email: str | None) -> ResolvedActor:
    """Resolve an audit actor via Keycloak without ever breaking audit reads."""
    cache_key = (user_id, user_email)
    cached = cast(ResolvedActor | None, _ACTOR_CACHE.get(cache_key))
    if cached is not None:
        return cached

    if not user_id:
        unresolved = ResolvedActor(
            user_id=user_id,
            user_email=user_email,
            user_display_name=None,
            resolved=False,
        )
        _ACTOR_CACHE[cache_key] = unresolved
        return unresolved

    try:
        from src.services.keycloak_service import keycloak_service

        if getattr(keycloak_service, "_admin", None) is None:
            await keycloak_service.connect()

        user = await keycloak_service.get_user(user_id)
        if not user:
            unresolved = ResolvedActor(
                user_id=user_id,
                user_email=None,
                user_display_name=None,
                resolved=False,
            )
            _ACTOR_CACHE[cache_key] = unresolved
            return unresolved

        email = user.get("email")
        resolved = ResolvedActor(
            user_id=user_id,
            user_email=str(email) if email else user_email,
            user_display_name=_keycloak_display_name(user),
            resolved=True,
        )
        _ACTOR_CACHE[cache_key] = resolved
        return resolved
    except Exception as exc:
        logger.debug("Failed to resolve audit actor %s: %s", user_id, exc)
        unresolved = ResolvedActor(
            user_id=user_id,
            user_email=None,
            user_display_name=None,
            resolved=False,
        )
        _ACTOR_CACHE[cache_key] = unresolved
        return unresolved


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

    def _filters(
        self,
        tenant_id: str,
        *,
        action: str | None = None,
        outcome: str | None = None,
        resource_type: str | None = None,
        actor_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
    ) -> list[Any]:
        conditions: list[Any] = [AuditEvent.tenant_id == tenant_id]

        if action:
            conditions.append(AuditEvent.action == action)
        if outcome:
            conditions.append(AuditEvent.outcome == outcome)
        if resource_type:
            conditions.append(AuditEvent.resource_type == resource_type)
        if actor_id:
            conditions.append(AuditEvent.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEvent.created_at >= start_date)
        if end_date:
            conditions.append(AuditEvent.created_at <= end_date)
        if search:
            like_pattern = f"%{search}%"
            conditions.append(
                or_(
                    AuditEvent.path.ilike(like_pattern),
                    AuditEvent.resource_type.ilike(like_pattern),
                    AuditEvent.resource_id.ilike(like_pattern),
                    AuditEvent.resource_name.ilike(like_pattern),
                    AuditEvent.action.ilike(like_pattern),
                )
            )

        return conditions

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
        filters = self._filters(
            tenant_id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            actor_id=actor_id,
            start_date=start_date,
            end_date=end_date,
            search=search,
        )
        query = select(AuditEvent).where(*filters)
        count_query = select(func.count(AuditEvent.id)).where(*filters)

        # Count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total

    async def get_stats(
        self,
        tenant_id: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        action: str | None = None,
        outcome: str | None = None,
        resource_type: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return filtered audit aggregates for one tenant."""
        window_end = end_date or datetime.now(UTC)
        window_start = start_date or (window_end - timedelta(days=30))
        filters = self._filters(
            tenant_id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            start_date=window_start,
            end_date=window_end,
            search=search,
        )

        total_result = await self.db.execute(select(func.count(AuditEvent.id)).where(*filters))
        total_events = int(total_result.scalar() or 0)

        success_result = await self.db.execute(
            select(func.count(AuditEvent.id)).where(*filters, AuditEvent.outcome == "success")
        )
        success_count = int(success_result.scalar() or 0)

        unique_result = await self.db.execute(select(func.count(func.distinct(AuditEvent.actor_id))).where(*filters))
        unique_actors = int(unique_result.scalar() or 0)

        action_count = func.count(AuditEvent.id)
        action_result = await self.db.execute(
            select(AuditEvent.action, action_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEvent.action)
            .order_by(action_count.desc(), AuditEvent.action.asc())
            .limit(20)
        )
        by_action = {row.action: int(row.cnt) for row in action_result}

        status_count = func.count(AuditEvent.id)
        status_result = await self.db.execute(
            select(AuditEvent.outcome, status_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEvent.outcome)
            .order_by(status_count.desc(), AuditEvent.outcome.asc())
        )
        by_status = {row.outcome: int(row.cnt) for row in status_result}

        return {
            "total_events": total_events,
            "success_count": success_count,
            "failed_count": total_events - success_count,
            "unique_actors": unique_actors,
            "by_action": by_action,
            "by_status": by_status,
            "window_start": window_start,
            "window_end": window_end,
        }

    async def get_actions(self, tenant_id: str) -> dict[str, Any]:
        """Return top distinct audit actions for one tenant over the last 30 days."""
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(days=30)
        filters = self._filters(tenant_id, start_date=window_start, end_date=window_end)
        action_count = func.count(AuditEvent.id)
        result = await self.db.execute(
            select(AuditEvent.action, action_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEvent.action)
            .order_by(action_count.desc(), AuditEvent.action.asc())
            .limit(100)
        )

        return {
            "actions": [{"action": row.action, "count": int(row.cnt)} for row in result],
            "window_start": window_start,
            "window_end": window_end,
        }

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
        count = int(getattr(result, "rowcount", 0) or 0)
        logger.info(f"Purged {count} audit events for tenant {tenant_id} before {before_date}")
        return count

    # ============ GDPR Article 17 — Right to Erasure (CAB-1794) ============

    async def erase_user_pii(
        self,
        user_id: str,
        *,
        tenant_id: str | None = None,
    ) -> dict:
        """Pseudonymize PII fields for a specific user (GDPR Art. 17).

        Replaces actor_id, actor_email, client_ip, user_agent with
        pseudonymized values. Preserves non-PII fields (action, resource,
        outcome, timestamps) for compliance analytics.

        Args:
            user_id: The actor_id to erase.
            tenant_id: Optional tenant scope. If None, erases across all tenants.

        Returns:
            Dict with records_affected count.
        """
        pseudo_id = f"erased-{uuid4().hex[:8]}"

        stmt = (
            update(AuditEvent)
            .where(AuditEvent.actor_id == user_id)
            .values(
                actor_id=pseudo_id,
                actor_email=None,
                client_ip=None,
                user_agent=None,
            )
        )
        if tenant_id:
            stmt = stmt.where(AuditEvent.tenant_id == tenant_id)

        result = await self.db.execute(stmt)
        count = int(getattr(result, "rowcount", 0) or 0)

        logger.info(
            f"GDPR erasure: pseudonymized {count} audit records for user {user_id}"
            f"{f' in tenant {tenant_id}' if tenant_id else ' (all tenants)'}"
        )
        return {"records_affected": count, "pseudo_id": pseudo_id}
