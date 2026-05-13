"""Audit service — PostgreSQL-backed compliance audit trail (CAB-1475).

Provides:
- Write: append-only audit event creation (called by middleware)
- Read: paginated queries with filters (called by router)
- Export: bulk query for CSV/JSON export
- Retention: configurable per-tenant cleanup
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from cachetools import TTLCache  # type: ignore[import-untyped]
from sqlalchemy import func, insert, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_chain import AuditChainHead, AuditEventRedactedView, PseudonymizedAuditErasure
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
_AUDIT_CHAIN_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtext(:tenant_id)::bigint)")


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


def _compute_audit_row_hash(
    prev_hash: bytes,
    *,
    event_id: str,
    created_at: datetime,
    tenant_id: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
) -> bytes:
    """Compute ADR-068 §4.5 row_hash in the exact canonical field order."""
    hasher = hashlib.sha256()
    hasher.update(prev_hash)
    for component in (
        event_id,
        created_at.isoformat(),
        tenant_id,
        actor_id or "",
        action,
        f"{resource_type}:{resource_id or ''}",
        outcome,
    ):
        hasher.update(component.encode("utf-8"))
    return hasher.digest()


def _wrap_pseudonymization_key(raw_key: bytes) -> bytes:
    """Application-layer wrap for the pseudonymization key (ADR-069 §4.2).

    DRAFT seam. Today it returns the raw key unchanged. Sign-off on
    CAB-2226 (DPO + Security) MUST decide before merge whether to:
      (a) wrap with a Vault-derived master key (KMS-style envelope), or
      (b) amend ADR-069 to accept raw storage because the DB itself is
          the trust boundary.

    DO NOT MERGE this PR until that decision is recorded on CAB-2226.
    """
    # TODO(CAB-2226 DPO sign-off): replace with Vault wrap; see ADR-069 §4.2.
    return raw_key


class AuditService:
    """Service for compliance-grade audit trail operations.

    CAB-2226 uses tenant-scoped transaction advisory locks because SELECT ... FOR UPDATE on a missing chain-head row
    cannot serialize the first two events for a tenant.
    """

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
        event_id: str | None = None,
        created_at: datetime | None = None,
    ) -> AuditEvent | None:
        """Record an immutable audit event.

        Returns the AuditEvent on success; returns None and logs ERROR on any
        persistence failure (CAB-1475 contract, preserved by CAB-2226). A
        future PR will replace this best-effort path with a durable outbox so
        that the function can flip to fail-loud per DORA Art.5.
        """
        try:
            await self.db.execute(_AUDIT_CHAIN_LOCK_SQL, {"tenant_id": tenant_id})
            head = await self.db.scalar(select(AuditChainHead).where(AuditChainHead.tenant_id == tenant_id))
            prev_hash = bytes(head.last_row_hash) if head is not None else b""
            event_created_at = created_at or datetime.now(UTC)
            event = AuditEvent(
                id=event_id or str(uuid4()),
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
                created_at=event_created_at,
            )
            event.row_hash = _compute_audit_row_hash(
                prev_hash,
                event_id=event.id,
                created_at=event.created_at,
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
            )
            self.db.add(event)
            await self.db.flush()

            chain_insert = pg_insert(AuditChainHead.__table__).values(
                tenant_id=tenant_id,
                last_row_hash=event.row_hash,
                last_event_id=event.id,
                updated_at=datetime.now(UTC),
            )
            await self.db.execute(
                chain_insert.on_conflict_do_update(
                    index_elements=[AuditChainHead.tenant_id],
                    set_={
                        "last_row_hash": chain_insert.excluded.last_row_hash,
                        "last_event_id": chain_insert.excluded.last_event_id,
                        "updated_at": func.now(),
                    },
                )
            )
            # CAB-2226: lock, audit row, and chain head share the caller-owned transaction and commit together.
            return event
        except Exception as e:
            # TODO(CAB-2226 follow-up): wire a durable outbox + replay so we can
            # flip this to fail-loud per DORA Art.5. Until then we honour the
            # original CAB-1475 contract: never raise; log + return None.
            logger.error(f"Failed to record audit event: {e}")
            return None

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
        conditions: list[Any] = [AuditEventRedactedView.tenant_id == tenant_id]

        if action:
            conditions.append(AuditEventRedactedView.action == action)
        if outcome:
            conditions.append(AuditEventRedactedView.outcome == outcome)
        if resource_type:
            conditions.append(AuditEventRedactedView.resource_type == resource_type)
        if actor_id:
            conditions.append(AuditEventRedactedView.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEventRedactedView.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventRedactedView.created_at <= end_date)
        if search:
            like_pattern = f"%{search}%"
            conditions.append(
                or_(
                    AuditEventRedactedView.path.ilike(like_pattern),
                    AuditEventRedactedView.resource_type.ilike(like_pattern),
                    AuditEventRedactedView.resource_id.ilike(like_pattern),
                    AuditEventRedactedView.resource_name.ilike(like_pattern),
                    AuditEventRedactedView.action.ilike(like_pattern),
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
    ) -> tuple[list[AuditEventRedactedView], int]:
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
        query = select(AuditEventRedactedView).where(*filters)
        count_query = select(func.count(AuditEventRedactedView.id)).where(*filters)

        # Count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(AuditEventRedactedView.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
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

        total_result = await self.db.execute(select(func.count(AuditEventRedactedView.id)).where(*filters))
        total_events = int(total_result.scalar() or 0)

        success_result = await self.db.execute(
            select(func.count(AuditEventRedactedView.id)).where(*filters, AuditEventRedactedView.outcome == "success")
        )
        success_count = int(success_result.scalar() or 0)

        unique_result = await self.db.execute(
            select(func.count(func.distinct(AuditEventRedactedView.actor_id))).where(*filters)
        )
        unique_actors = int(unique_result.scalar() or 0)

        action_count = func.count(AuditEventRedactedView.id)
        action_result = await self.db.execute(
            select(AuditEventRedactedView.action, action_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEventRedactedView.action)
            .order_by(action_count.desc(), AuditEventRedactedView.action.asc())
            .limit(20)
        )
        by_action = {row.action: int(row.cnt) for row in action_result}

        status_count = func.count(AuditEventRedactedView.id)
        status_result = await self.db.execute(
            select(AuditEventRedactedView.outcome, status_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEventRedactedView.outcome)
            .order_by(status_count.desc(), AuditEventRedactedView.outcome.asc())
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
        action_count = func.count(AuditEventRedactedView.id)
        result = await self.db.execute(
            select(AuditEventRedactedView.action, action_count.label("cnt"))
            .where(*filters)
            .group_by(AuditEventRedactedView.action)
            .order_by(action_count.desc(), AuditEventRedactedView.action.asc())
            .limit(100)
        )

        return {
            "actions": [{"action": row.action, "count": int(row.cnt)} for row in result],
            "window_start": window_start,
            "window_end": window_end,
        }

    async def get_event(self, event_id: str) -> AuditEventRedactedView | None:
        """Get a single audit event by ID."""
        result = await self.db.execute(select(AuditEventRedactedView).where(AuditEventRedactedView.id == event_id))
        return cast(AuditEventRedactedView | None, result.scalar_one_or_none())

    # ============ Export ============

    async def export_events(
        self,
        tenant_id: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10000,
    ) -> list[AuditEventRedactedView]:
        """Export audit events for a tenant (bulk query for CSV/JSON export)."""
        query = select(AuditEventRedactedView).where(AuditEventRedactedView.tenant_id == tenant_id)

        if start_date:
            query = query.where(AuditEventRedactedView.created_at >= start_date)
        if end_date:
            query = query.where(AuditEventRedactedView.created_at <= end_date)

        query = query.order_by(AuditEventRedactedView.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============ Stats ============

    async def get_summary(
        self,
        tenant_id: str | None = None,
    ) -> dict:
        """Get audit summary stats. If tenant_id is None, returns global stats."""
        base = select(func.count(AuditEventRedactedView.id))
        if tenant_id:
            base = base.where(AuditEventRedactedView.tenant_id == tenant_id)

        total_result = await self.db.execute(base)
        total = total_result.scalar() or 0

        # Count by outcome
        outcomes = {}
        for outcome_val in ("success", "failure", "denied", "error"):
            q = base.where(AuditEventRedactedView.outcome == outcome_val)
            r = await self.db.execute(q)
            outcomes[outcome_val] = r.scalar() or 0

        # Count by action (top 10)
        action_q = (
            select(AuditEventRedactedView.action, func.count(AuditEventRedactedView.id).label("cnt"))
            .group_by(AuditEventRedactedView.action)
            .order_by(func.count(AuditEventRedactedView.id).desc())
            .limit(10)
        )
        if tenant_id:
            action_q = action_q.where(AuditEventRedactedView.tenant_id == tenant_id)
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
        """Application code may not delete immutable audit_events after CAB-2226."""
        raise NotImplementedError(
            f"CAB-2226 makes audit_events append-only; retention for {tenant_id} before {before_date.isoformat()} "
            "must use an approved archive/partition process."
        )

    # ============ GDPR Article 17 — Right to Erasure (CAB-1794) ============

    async def erase_user_pii(
        self,
        user_id: str,
        dpo_approver_id: str,
        legal_basis: str,
        redaction_map: dict,
        scope_event_ids: list[str] | None = None,
    ) -> dict:
        """Record a GDPR Art.17 audit erasure without mutating audit_events."""
        erasure_id = uuid4()
        now = datetime.now(UTC)
        event_scope = scope_event_ids or []
        await self.db.execute(
            insert(PseudonymizedAuditErasure.__table__).values(
                erasure_id=erasure_id,
                request_received_at=now,
                legal_basis=legal_basis,
                dpo_approver_id=dpo_approver_id,
                dpo_approved_at=now,
                subject_external_ref=None,
                pseudonymization_key=_wrap_pseudonymization_key(secrets.token_bytes(32)),
                scope_actor_ids=[user_id],
                scope_event_ids=event_scope,
                redaction_map=redaction_map,
                created_at=now,
            )
        )

        logger.info(
            "GDPR erasure recorded without audit_events mutation for user %s by DPO approver %s",
            user_id,
            dpo_approver_id,
        )
        return {
            "erasure_id": str(erasure_id),
            "records_affected": 0,
            "scope_actor_ids": [user_id],
            "scope_event_ids": event_scope,
        }
