"""Issue and atomically consume MCP approval tokens."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.approval_token import ApprovalToken, ApprovalTokenStatus
from src.services.approval_token_signer import ApprovalTokenSigner
from src.services.audit_service import AuditService
from src.utils.canonical_json import canonical_hash

RejectReason = Literal["replay", "scope_mismatch", "arguments_mismatch", "expired"]


@dataclass(frozen=True)
class IssueResult:
    approval_token: str
    jti: uuid.UUID
    expires_at: datetime


@dataclass(frozen=True)
class ConsumeResult:
    consumed: bool
    reason: RejectReason | None = None


class ApprovalTokenService:
    def __init__(self, db: AsyncSession, signer: ApprovalTokenSigner | None = None) -> None:
        self.db = db
        self.signer = signer
        self.audit = AuditService(db)

    async def issue(
        self,
        *,
        tenant_id: str,
        tool_name: str,
        tool_call_id: uuid.UUID,
        arguments: Any,
        policy_version: str,
        contract_version: str,
        requester_actor_id: str,
        approver_actor_id: str,
    ) -> IssueResult:
        if approver_actor_id == requester_actor_id:
            raise ValueError("approver_actor_id must differ from requester_actor_id")
        if self.signer is None:
            raise ValueError("approval token signer is required")

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.signer.ttl_seconds)
        row = ApprovalToken(
            tenant_id=tenant_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments_hash=canonical_hash(arguments),
            policy_version=policy_version,
            contract_version=contract_version,
            requester_actor_id=requester_actor_id,
            approver_actor_id=approver_actor_id,
            issued_at=now,
            expires_at=expires_at,
            status=ApprovalTokenStatus.ISSUED.value,
        )
        self.db.add(row)
        await self.db.flush()
        token = self.signer.sign(
            {
                "jti": str(row.jti),
                "tool_call_id": str(tool_call_id),
                "tenant_id": tenant_id,
                "tool_name": tool_name,
                "arguments_hash": row.arguments_hash,
                "policy_version": policy_version,
                "contract_version": contract_version,
                "requester_actor_id": requester_actor_id,
                "approver_actor_id": approver_actor_id,
            },
            issued_at=now,
            expires_at=expires_at,
        )
        await self.audit.record_event(
            tenant_id=tenant_id,
            action="approval_token_issued",
            method="POST",
            path=f"/v1/tenants/{tenant_id}/tool-approvals",
            resource_type="mcp_tool_call",
            resource_id=tool_name,
            actor_id=approver_actor_id,
            correlation_id=str(tool_call_id),
            details={
                "jti": str(row.jti),
                "requester_actor_id": requester_actor_id,
                "approver_actor_id": approver_actor_id,
                "arguments_hash": row.arguments_hash,
            },
        )
        return IssueResult(approval_token=token, jti=row.jti, expires_at=expires_at)

    async def consume(self, *, jti: uuid.UUID, tenant_id: str, tool_name: str, arguments_hash: str) -> ConsumeResult:
        now = datetime.now(UTC)
        stmt = (
            update(ApprovalToken)
            .where(ApprovalToken.jti == jti, ApprovalToken.consumed_at.is_(None))
            .values(consumed_at=now, status=ApprovalTokenStatus.CONSUMED.value)
            .returning(ApprovalToken)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            await self._audit_rejected(tenant_id, tool_name, str(jti), "replay")
            return ConsumeResult(consumed=False, reason="replay")

        reason: RejectReason | None = None
        if row.tenant_id != tenant_id or row.tool_name != tool_name:
            reason = "scope_mismatch"
        elif row.arguments_hash != arguments_hash:
            reason = "arguments_mismatch"
        else:
            expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                reason = "expired"

        if reason:
            await self._audit_rejected(row.tenant_id, row.tool_name, str(row.jti), reason)
            return ConsumeResult(consumed=False, reason=reason)

        await self.audit.record_event(
            tenant_id=row.tenant_id,
            action="approval_token_used",
            method="POST",
            path="/v1/internal/approval-tokens/consume",
            resource_type="mcp_tool_call",
            resource_id=row.tool_name,
            actor_id="stoa-gateway",
            actor_type="service",
            correlation_id=str(row.tool_call_id),
            details={"jti": str(row.jti), "arguments_hash": row.arguments_hash},
        )
        return ConsumeResult(consumed=True)

    async def _audit_rejected(self, tenant_id: str, tool_name: str, jti: str, reason: RejectReason) -> None:
        await self.audit.record_event(
            tenant_id=tenant_id,
            action="approval_token_rejected",
            method="POST",
            path="/v1/internal/approval-tokens/consume",
            resource_type="mcp_tool_call",
            resource_id=tool_name,
            actor_id="stoa-gateway",
            actor_type="service",
            outcome="denied",
            details={"jti": jti, "reason": reason},
        )
