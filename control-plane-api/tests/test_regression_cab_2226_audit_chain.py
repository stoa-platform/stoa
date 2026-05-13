"""CAB-2226 audit-chain regression tests."""

# Integration test requires migration 107 applied.
# regression for CAB-2226
from __future__ import annotations

import asyncio
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.services.audit_service import AuditService, _compute_audit_row_hash


def _empty_result() -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = 0
    result.scalars.return_value.all.return_value = []
    return result


class _ChainSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.head: tuple[bytes, str] | None = None
        self.prev_hashes: list[bytes] = []

    def add(self, event: Any) -> None:
        self.added.append(event)

    async def flush(self) -> None:
        return None

    async def execute(self, statement: Any, _params: dict[str, Any] | None = None) -> Any:
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            return _empty_result()
        if "SELECT" in sql and "audit_chain_heads" in sql:
            prev_hash = b"" if self.head is None else self.head[0]
            self.prev_hashes.append(prev_hash)
            return MagicMock(one_or_none=MagicMock(return_value=self.head))
        if "INSERT INTO audit_chain_heads" in sql:
            event = self.added[-1]
            self.head = (event.row_hash, event.id)
            return _empty_result()
        raise AssertionError(f"unexpected SQL: {sql}")


class _SpySession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, _params: dict[str, Any] | None = None) -> MagicMock:
        self.statements.append(statement)
        return _empty_result()


def _compiled_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect())).lower()


def _row_hash_kwargs(row: Any) -> dict[str, Any]:
    keys = ("id", "created_at", "tenant_id", "actor_id", "action", "resource_type", "resource_id", "outcome")
    kwargs = {key: row[key] for key in keys}
    kwargs["event_id"] = kwargs.pop("id")
    return kwargs


def test_hash_determinism_same_inputs_same_row_hash() -> None:
    kwargs = {
        "event_id": "evt-1",
        "created_at": datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        "tenant_id": "tenant-1",
        "actor_id": "actor-1",
        "action": "create",
        "resource_type": "subscription",
        "resource_id": "sub-1",
        "outcome": "success",
    }

    first = _compute_audit_row_hash(b"previous", **kwargs)
    assert first == _compute_audit_row_hash(b"previous", **kwargs)
    assert len(first) == 32


@pytest.mark.asyncio
async def test_hash_chain_progression_advances_chain_head_three_times() -> None:
    session = _ChainSession()
    service = AuditService(session)  # type: ignore[arg-type]
    created_at = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)

    events = [
        await service.record_event(
            tenant_id="tenant-1",
            action="create",
            method="POST",
            path="/v1/subscriptions",
            resource_type="subscription",
            resource_id=f"sub-{idx}",
            actor_id="actor-1",
            event_id=f"evt-{idx}",
            created_at=created_at + timedelta(seconds=idx),
        )
        for idx in range(3)
    ]

    hashes = [event.row_hash for event in events]
    assert session.prev_hashes == [b"", hashes[0], hashes[1]]
    assert len(set(hashes)) == 3
    assert session.head == (hashes[-1], events[-1].id)


@pytest.mark.asyncio
async def test_erase_user_pii_inserts_auxiliary_record_without_audit_update() -> None:
    session = _SpySession()
    service = AuditService(session)  # type: ignore[arg-type]

    await service.erase_user_pii(
        "user-1",
        dpo_approver_id="dpo-1",
        legal_basis="GDPR Art.17",
        redaction_map={"actor_email": None, "client_ip": None},
        scope_event_ids=["evt-1"],
    )

    sql = "\n".join(_compiled_sql(statement) for statement in session.statements)
    assert "insert into pseudonymized_audit_erasures" in sql
    assert "update audit_events" not in sql


@pytest.mark.asyncio
async def test_list_events_reads_from_redacted_view() -> None:
    session = _SpySession()
    service = AuditService(session)  # type: ignore[arg-type]

    events, total = await service.list_events("tenant-1")

    sql = "\n".join(_compiled_sql(statement) for statement in session.statements)
    assert events == []
    assert total == 0
    assert "from audit_events_redacted" in sql
    assert re.search(r"from\s+audit_events(?!_redacted)\b", sql) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_same_tenant_inserts_do_not_reuse_previous_hash() -> None:
    """Requires a real PostgreSQL DATABASE_URL with migration 107 applied."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as conn:
            objects = await conn.execute(
                text(
                    "SELECT to_regclass('audit_chain_heads') AS heads, "
                    "to_regclass('audit_events_redacted') AS view_name"
                )
            )
            row = objects.mappings().one()
            if row["heads"] is None or row["view_name"] is None:
                pytest.skip("migration 107_audit_immutability_pseudonymization is not applied")

        tenant_id = f"cab-2226-{uuid4()}"
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def emit(index: int) -> str:
            async with session_factory() as session:
                event = await AuditService(session).record_event(
                    tenant_id=tenant_id,
                    actor_id=f"actor-{index}",
                    action="cab_2226_concurrency",
                    method="POST",
                    path="/cab-2226/concurrency",
                    resource_type="audit_test",
                    resource_id=f"resource-{index}",
                    outcome="success",
                )
                await session.commit()
                return event.id

        await asyncio.gather(emit(1), emit(2))

        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, created_at, tenant_id, actor_id, action, resource_type, resource_id, outcome, row_hash "
                    "FROM audit_events WHERE tenant_id = :tenant_id ORDER BY created_at ASC"
                ),
                {"tenant_id": tenant_id},
            )
            rows = result.mappings().all()
            head = await session.execute(
                text("SELECT last_row_hash, last_event_id FROM audit_chain_heads WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
            chain_head = head.mappings().one()

        assert len(rows) == 2
        first_hash = _compute_audit_row_hash(b"", **_row_hash_kwargs(rows[0]))
        second_hash = _compute_audit_row_hash(first_hash, **_row_hash_kwargs(rows[1]))

        assert bytes(rows[0]["row_hash"]) == first_hash
        assert bytes(rows[1]["row_hash"]) == second_hash
        assert bytes(chain_head["last_row_hash"]) == second_hash
        assert chain_head["last_event_id"] == rows[1]["id"]
    finally:
        await engine.dispose()
