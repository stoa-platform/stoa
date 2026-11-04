"""Build and sign one tenant's tool-permission policy snapshot.

A snapshot pairs the tenant's permission rows with the version the DB trigger
assigned to them. Publication over HTTP is a separate concern.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenant import Tenant
from ..models.tenant_tool_permission import TenantToolPermission
from ..models.tool_policy_version import ToolPolicyVersion
from ..schemas.tool_permission_policy import MAX_POLICY_ENTRIES, ToolPermissionPolicy, ToolPermissionPolicyEntry
from .policy_artifact_signer import sign_policy_artifact

SNAPSHOT_ATTEMPTS = 3


class PolicySnapshotError(Exception):
    """Snapshot refused; ``code`` is stable and carries no tenant data."""

    code = "policy_snapshot_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class PolicySnapshotTooLargeError(PolicySnapshotError):
    """The tenant holds more rules than one policy may carry."""

    code = "policy_entries_exceed_cap"


class PolicySnapshotConflictError(PolicySnapshotError):
    """Permissions kept changing while the rows were being read."""

    code = "policy_snapshot_conflict"


class PolicySnapshotUnknownTenantError(PolicySnapshotError):
    """No tenant row carries the requested identity, so no UUID can be issued."""

    code = "policy_tenant_unknown"


@dataclass(frozen=True)
class IssuedToolPolicy:
    """A validated policy next to its compact JWS form."""

    policy: ToolPermissionPolicy
    artifact: str


async def _read_identity(db: AsyncSession, tenant_id: str) -> tuple[UUID, int]:
    """The tenant's UUID next to its counter, read in one statement.

    A missing counter row is the documented baseline (see ToolPolicyVersion); a
    missing tenant row is refused rather than given an invented identity.
    """
    counter = select(ToolPolicyVersion.version).where(ToolPolicyVersion.tenant_id == Tenant.id).scalar_subquery()
    identity = (await db.execute(select(Tenant.uuid, counter).where(Tenant.id == tenant_id))).one_or_none()
    if identity is None:
        raise PolicySnapshotUnknownTenantError()
    return identity[0], identity[1] or 1


async def snapshot_tool_policy(
    db: AsyncSession, tenant_id: str, *, issued_at: datetime | None = None
) -> ToolPermissionPolicy:
    """Pair the tenant's rules with the identity and version they belong to.

    The tenant UUID and the counter are read on both sides of the row scan: a change
    in between means a mutation or a recreation landed mid-read, so the scan restarts
    rather than mislabel the rules.
    """
    rows_query = (
        select(TenantToolPermission.mcp_server_id, TenantToolPermission.tool_name, TenantToolPermission.allowed)
        .where(TenantToolPermission.tenant_id == tenant_id)
        .order_by(TenantToolPermission.mcp_server_id, TenantToolPermission.tool_name)
        .limit(MAX_POLICY_ENTRIES + 1)
    )
    for _ in range(SNAPSHOT_ATTEMPTS):
        tenant_uuid, version = await _read_identity(db, tenant_id)
        rows = (await db.execute(rows_query)).all()
        if await _read_identity(db, tenant_id) != (tenant_uuid, version):
            continue
        if len(rows) > MAX_POLICY_ENTRIES:
            raise PolicySnapshotTooLargeError()
        return ToolPermissionPolicy.issue(
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            version=version,
            permissions=[
                ToolPermissionPolicyEntry(mcp_server=str(server), tool=tool, allowed=allowed)
                for server, tool, allowed in rows
            ],
            issued_at=issued_at or datetime.now(UTC),
        )
    raise PolicySnapshotConflictError()


async def issue_tool_policy_artifact(
    db: AsyncSession, tenant_id: str, *, issued_at: datetime | None = None
) -> IssuedToolPolicy:
    """Snapshot the tenant, then hand the validated payload to the signer unchanged."""
    policy = await snapshot_tool_policy(db, tenant_id, issued_at=issued_at)
    return IssuedToolPolicy(policy=policy, artifact=sign_policy_artifact(policy.model_dump(mode="json")))
