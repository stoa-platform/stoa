from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.internal_hmac import verify_internal_hmac
from src.database import get_db
from src.models.audit_emit_idempotency import AuditEmitIdempotency
from src.services.audit_service import AuditService

router = APIRouter(prefix="/v1/internal", tags=["Internal - Audit"])


class AuditEmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["stoa-gateway"]
    event_type: Literal["TOOL_CALL_DECISION"]
    decision: Literal["allow", "deny"]
    reason: str
    tenant_id: UUID
    actor_id: UUID | None
    session_id: str | None
    resource_type: Literal["mcp_tool"]
    resource_id: str
    tool_call_id: UUID
    approval_id: UUID | None
    policy_version: str | None
    correlation_id: UUID
    occurred_at: datetime
    details: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("occurred_at must be ISO8601 UTC")
        return value


@router.post("/audit/emit", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_internal_hmac)])
async def emit_audit_event(
    payload: AuditEmitRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    event_id = str(uuid4())
    stmt = insert(AuditEmitIdempotency).values(key=idempotency_key, event_id=event_id)
    result = await db.execute(stmt.on_conflict_do_nothing(index_elements=[AuditEmitIdempotency.key]))
    if result.rowcount == 0:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    audit_details: dict[str, Any] = {
        "reason": payload.reason,
        "tool_call_id": str(payload.tool_call_id),
        "approval_id": str(payload.approval_id) if payload.approval_id else None,
        "policy_version": payload.policy_version,
        "source": payload.source,
        "decision": payload.decision,
        "session_id": payload.session_id,
        "gateway_details": payload.details,
    }
    event = await AuditService(db).record_event(
        tenant_id=str(payload.tenant_id),
        action=payload.event_type.lower(),
        method="POST",
        path="/v1/internal/audit/emit",
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        actor_id=str(payload.actor_id) if payload.actor_id else None,
        actor_type="service",
        outcome="failure" if payload.decision == "deny" else "success",
        status_code=status.HTTP_202_ACCEPTED,
        correlation_id=str(payload.correlation_id),
        details=audit_details,
        event_id=event_id,
        created_at=payload.occurred_at,
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record audit event")
    return Response(status_code=status.HTTP_202_ACCEPTED)
