"""Per-tenant policy snapshots built from permission rows and the version counter."""

import base64
import json
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.models.tenant import Tenant
from src.models.tenant_tool_permission import TenantToolPermission
from src.models.tool_policy_version import ToolPolicyVersion
from src.schemas.tool_permission_policy import MAX_POLICY_ENTRIES
from src.services.tool_policy_snapshot import (
    PolicySnapshotConflictError,
    PolicySnapshotTooLargeError,
    PolicySnapshotUnknownTenantError,
    issue_tool_policy_artifact,
    snapshot_tool_policy,
)

ISSUED_AT = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
# Letters keep the hex form textual under SQLite's NUMERIC affinity for the UUID column.
SERVER_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SERVER_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
TENANT = "tenant-a"
CLAIMS = {"iss", "aud", "tenant_id", "tenant_uuid", "version", "issued_at", "expires_at", "permissions"}
# Identities an equality predicate must not confuse with TENANT.
LOOKALIKES = ["tenant-ab", "tenant-", "TENANT-A", "tenant-a ", "tenant-a%", "tenant_a"]


def row(tenant: str, server: UUID, tool: str, allowed: bool = True) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "tenant_id": tenant,
        "mcp_server_id": server,
        "tool_name": tool,
        "allowed": allowed,
        "created_by": "test",
        "created_at": ISSUED_AT,
        "updated_at": ISSUED_AT,
    }


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # A WAL file lets a second connection commit while a snapshot read is in flight.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'policy.db'}")
    async with engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(TenantToolPermission.__table__.create)
        await connection.run_sync(ToolPolicyVersion.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def seed(
    db: async_sessionmaker[AsyncSession],
    rows: list[dict[str, Any]],
    versions: dict[str, int],
    tenants: Iterable[str] | None = None,
) -> None:
    # By default every tenant named by a row or a counter also exists as a tenant.
    known = set(tenants) if tenants is not None else {*versions, *(row["tenant_id"] for row in rows)}
    async with db.begin() as session:
        session.add_all(Tenant(id=tenant, name=tenant) for tenant in sorted(known))
        if rows:
            await session.execute(insert(TenantToolPermission), rows)
        session.add_all(ToolPolicyVersion(tenant_id=tenant, version=version) for tenant, version in versions.items())


@pytest.fixture
def signing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ed25519.Ed25519PrivateKey:
    key = ed25519.Ed25519PrivateKey.generate()
    path = tmp_path / "ephemeral-key"
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KEY_FILE", str(path))
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KID", "cp-policy-202611-1")
    return key


def decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


async def test_snapshot_carries_every_rule_in_stable_order(db) -> None:
    rows = [row(TENANT, s, f"tool-{i:03d}", i % 3 != 0) for i in range(60) for s in (SERVER_B, SERVER_A)]
    await seed(db, rows, {TENANT: 7})
    async with db() as session:
        policy = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
    assert policy.tenant_id == TENANT and policy.version == 7 and policy.issued_at == ISSUED_AT
    assert len(policy.permissions) == 120
    expected = sorted((str(r["mcp_server_id"]), r["tool_name"], r["allowed"]) for r in rows)
    assert [(e.mcp_server, e.tool, e.allowed) for e in policy.permissions] == expected


@pytest.mark.parametrize("retained_version", [None, 5])
async def test_empty_tenant_yields_empty_policy_with_counter(db, retained_version: int | None) -> None:
    versions = {"other": 3} | ({TENANT: retained_version} if retained_version else {})
    await seed(db, [row("other", SERVER_A, "read")], versions, tenants=[TENANT, "other"])
    async with db() as session:
        policy = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
    assert policy.permissions == []
    assert policy.version == (retained_version or 1)


async def test_other_tenants_never_leak(db) -> None:
    rows = [row(TENANT, SERVER_A, "mine")]
    rows += [row(o, s, t) for o in LOOKALIKES for s in (SERVER_A, SERVER_B) for t in ("mine", "theirs")]
    await seed(db, rows, {TENANT: 2, **{other: 90 + index for index, other in enumerate(LOOKALIKES)}})
    async with db() as session:
        policy = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
        assert [(e.mcp_server, e.tool) for e in policy.permissions] == [(str(SERVER_A), "mine")]
        assert policy.version == 2
        for other in LOOKALIKES:
            assert len((await snapshot_tool_policy(session, other, issued_at=ISSUED_AT)).permissions) == 4


@pytest.mark.parametrize("version", [1, 2, 42, 2**40])
async def test_version_counter_is_propagated(db, signing_key: ed25519.Ed25519PrivateKey, version: int) -> None:
    await seed(db, [row(TENANT, SERVER_A, "read")], {TENANT: version})
    async with db() as session:
        issued = await issue_tool_policy_artifact(session, TENANT, issued_at=ISSUED_AT)
    assert issued.policy.version == version
    assert json.loads(decode(issued.artifact.split(".")[1]))["version"] == version


@pytest.mark.parametrize("count", [MAX_POLICY_ENTRIES, MAX_POLICY_ENTRIES + 1])
async def test_entry_cap_refuses_before_signing(db, count: int) -> None:
    # No signing key is configured: reaching the signer would surface a 503, not the cap error.
    await seed(db, [row(TENANT, SERVER_A, f"tool-{index}") for index in range(count)], {TENANT: 2})
    async with db() as session:
        if count > MAX_POLICY_ENTRIES:
            with pytest.raises(PolicySnapshotTooLargeError, match="policy_entries_exceed_cap"):
                await issue_tool_policy_artifact(session, TENANT, issued_at=ISSUED_AT)
        else:
            assert len((await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)).permissions) == count


@pytest.mark.parametrize("ttl", [900, 300])
async def test_issuance_signs_the_validated_payload(
    db, signing_key: ed25519.Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch, ttl: int
) -> None:
    monkeypatch.setattr(settings, "TOOL_PERMISSION_POLICY_TTL_SECONDS", ttl)
    await seed(db, [row(TENANT, SERVER_A, "read"), row(TENANT, SERVER_B, "write", False)], {TENANT: 2})
    async with db() as session:
        issued = await issue_tool_policy_artifact(session, TENANT, issued_at=ISSUED_AT)
    header, body, signature = issued.artifact.split(".")
    assert json.loads(decode(header)) == {"alg": "EdDSA", "typ": "stoa-tool-policy+jws", "kid": "cp-policy-202611-1"}
    payload = json.loads(decode(body))
    assert payload == issued.policy.model_dump(mode="json")
    assert set(payload) == CLAIMS
    assert payload["permissions"] == [
        {"mcp_server": str(SERVER_A), "tool": "read", "allowed": True},
        {"mcp_server": str(SERVER_B), "tool": "write", "allowed": False},
    ]
    assert (issued.policy.expires_at - issued.policy.issued_at).total_seconds() == ttl
    signing_key.public_key().verify(decode(signature), f"{header}.{body}".encode("ascii"))


async def test_issued_at_defaults_to_now(db, signing_key: ed25519.Ed25519PrivateKey) -> None:
    await seed(db, [], {}, tenants=[TENANT])
    before = datetime.now(UTC)
    async with db() as session:
        issued = await issue_tool_policy_artifact(session, TENANT)
    assert before <= issued.policy.issued_at <= datetime.now(UTC)


async def test_issuance_binds_configured_issuer_audience_and_stored_tenant_uuid(
    db, signing_key: ed25519.Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "STOA_POLICY_ISSUER", "cp-eu")
    monkeypatch.setattr(settings, "STOA_POLICY_AUDIENCE", "gw-eu")
    await seed(db, [row(TENANT, SERVER_A, "read")], {TENANT: 2})
    async with db() as session:
        stored = await session.scalar(select(Tenant.uuid).where(Tenant.id == TENANT))
        issued = await issue_tool_policy_artifact(session, TENANT, issued_at=ISSUED_AT)
    assert isinstance(stored, UUID) and issued.policy.tenant_uuid == stored
    body = json.loads(decode(issued.artifact.split(".")[1]))
    assert (body["iss"], body["aud"], body["tenant_uuid"]) == ("cp-eu", "gw-eu", str(stored))


async def test_distinct_and_recreated_tenants_carry_distinct_uuids(db) -> None:
    await seed(db, [], {}, tenants=[TENANT, "tenant-b"])
    async with db() as session:
        first = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
        other = await snapshot_tool_policy(session, "tenant-b", issued_at=ISSUED_AT)
    assert first.tenant_uuid != other.tenant_uuid
    # A slug deleted then recreated is a new tenant: the old artifact no longer matches it.
    async with db.begin() as session:
        await session.execute(delete(Tenant).where(Tenant.id == TENANT))
        session.add(Tenant(id=TENANT, name=TENANT))
    async with db() as session:
        recreated = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
    assert recreated.tenant_uuid not in {first.tenant_uuid, other.tenant_uuid}


async def test_unknown_tenant_is_refused_before_signing(db) -> None:
    # Rules and a counter without a tenant row never yield an invented identity.
    await seed(db, [row("ghost", SERVER_A, "read")], {"ghost": 4}, tenants=[TENANT])
    async with db() as session:
        with pytest.raises(PolicySnapshotUnknownTenantError, match="policy_tenant_unknown"):
            await issue_tool_policy_artifact(session, "ghost", issued_at=ISSUED_AT)
        assert (await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)).permissions == []


@pytest.mark.parametrize("keep_mutating", [False, True])
async def test_mutation_during_read_restarts_or_refuses(db, tmp_path: Path, keep_mutating: bool) -> None:
    await seed(db, [row(TENANT, SERVER_A, "read")], {TENANT: 2})
    writer = create_engine(f"sqlite:///{tmp_path / 'policy.db'}")
    fired = 0

    def commit_mutation(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        # Mirror the DB trigger from a second connection while the row scan is in flight.
        nonlocal fired
        if "FROM tenant_tool_permissions" in statement and (keep_mutating or fired == 0):
            fired += 1
            with writer.begin() as connection:
                connection.execute(insert(TenantToolPermission), [row(TENANT, SERVER_B, f"late-{fired}", False)])
                bump = update(ToolPolicyVersion).where(ToolPolicyVersion.tenant_id == TENANT)
                connection.execute(bump.values(version=ToolPolicyVersion.version + 1))

    event.listen(db.kw["bind"].sync_engine, "after_cursor_execute", commit_mutation)
    async with db() as session:
        if keep_mutating:
            with pytest.raises(PolicySnapshotConflictError, match="policy_snapshot_conflict"):
                await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
            assert fired == 3
        else:
            policy = await snapshot_tool_policy(session, TENANT, issued_at=ISSUED_AT)
            assert policy.version == 3
            assert [(e.tool, e.allowed) for e in policy.permissions] == [("read", True), ("late-1", False)]
    writer.dispose()
