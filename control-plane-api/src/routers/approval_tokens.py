"""CAB-2227 MCP destructive-tool approval tokens."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User
from src.auth.rbac import require_role
from src.config import settings
from src.database import get_db
from src.routers.gateway_internal import _validate_gateway_key
from src.services.approval_token_service import ApprovalTokenService, RejectReason
from src.services.approval_token_signer import signer_from_settings

router = APIRouter(tags=["Approval Tokens"])


class ToolApprovalRequest(BaseModel):
    requester_actor_id: str
    tool_name: str = Field(..., description="tenant:contract:operation")
    tool_call_id: uuid.UUID
    arguments: dict[str, Any] | None = None
    policy_version: str
    contract_version: str


class ToolApprovalResponse(BaseModel):
    approval_token: str
    jti: uuid.UUID
    expires_at: datetime


class ConsumeApprovalTokenRequest(BaseModel):
    jti: uuid.UUID
    tenant_id: str
    tool_name: str
    arguments_hash: str = Field(..., min_length=64, max_length=64)


class ConsumeApprovalTokenResponse(BaseModel):
    consumed: bool
    reason: RejectReason | None = None


def _gateway_key_or_401(x_gateway_key: str | None) -> None:
    _validate_gateway_key(x_gateway_key or "")


@router.post("/v1/tenants/{tenant_id}/tool-approvals", response_model=ToolApprovalResponse)
async def issue_tool_approval(
    tenant_id: str,
    request: ToolApprovalRequest,
    user: User = Depends(require_role(["tenant-admin", "cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> ToolApprovalResponse:
    if "cpi-admin" not in user.roles and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")
    try:
        result = await ApprovalTokenService(db, signer_from_settings(settings)).issue(
            tenant_id=tenant_id,
            tool_name=request.tool_name,
            tool_call_id=request.tool_call_id,
            arguments=request.arguments,
            policy_version=request.policy_version,
            contract_version=request.contract_version,
            requester_actor_id=request.requester_actor_id,
            approver_actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ToolApprovalResponse(
        approval_token=result.approval_token,
        jti=result.jti,
        expires_at=result.expires_at,
    )


@router.post(
    "/v1/internal/approval-tokens/consume",
    response_model=ConsumeApprovalTokenResponse,
    response_model_exclude_none=True,
)
async def consume_tool_approval(
    request: ConsumeApprovalTokenRequest,
    x_gateway_key: str | None = Header(None, alias="X-Gateway-Key"),
    db: AsyncSession = Depends(get_db),
) -> ConsumeApprovalTokenResponse | JSONResponse:
    _gateway_key_or_401(x_gateway_key)
    result = await ApprovalTokenService(db).consume(
        jti=request.jti,
        tenant_id=request.tenant_id,
        tool_name=request.tool_name,
        arguments_hash=request.arguments_hash,
    )
    if not result.consumed:
        return JSONResponse(
            status_code=409,
            content=ConsumeApprovalTokenResponse(consumed=False, reason=result.reason).model_dump(),
        )
    return ConsumeApprovalTokenResponse(consumed=True)


@router.get("/v1/internal/approval-tokens/jwks")
async def approval_token_jwks(x_gateway_key: str | None = Header(None, alias="X-Gateway-Key")) -> dict[str, Any]:
    _gateway_key_or_401(x_gateway_key)
    return signer_from_settings(settings).jwks()
