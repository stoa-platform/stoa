"""Chat Agent router — conversation CRUD + SSE message streaming (CAB-286).

Provides 11 endpoints:
  POST   /v1/tenants/{tenant_id}/chat/conversations              — create
  GET    /v1/tenants/{tenant_id}/chat/conversations              — list
  GET    /v1/tenants/{tenant_id}/chat/conversations/{id}         — get (with messages)
  PATCH  /v1/tenants/{tenant_id}/chat/conversations/{id}         — rename
  POST   /v1/tenants/{tenant_id}/chat/conversations/{id}/messages — send + stream
  PATCH  /v1/tenants/{tenant_id}/chat/conversations/{id}/archive — archive/restore
  DELETE /v1/tenants/{tenant_id}/chat/conversations/{id}         — delete
  DELETE /v1/tenants/{tenant_id}/chat/conversations              — cascade delete (tenant)
  DELETE /v1/tenants/{tenant_id}/chat/conversations/purge        — GDPR retention purge
  GET    /v1/tenants/{tenant_id}/chat/usage                      — token usage (user)
  GET    /v1/tenants/{tenant_id}/chat/usage/tenant               — token usage (admin)
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..auth import User, get_current_user, require_tenant_access
from ..config import settings
from ..database import get_db
from ..repositories.chat_token_usage_repository import ChatTokenUsageRepository
from ..schemas.chat import (
    ChatTenantUsageResponse,
    ChatUsageResponse,
    ConversationArchive,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageSend,
    TokenBudgetStatusResponse,
    TokenUsageStatsResponse,
)
from ..services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/chat",
    tags=["Chat"],
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    summary="Create a chat conversation",
)
@require_tenant_access
async def create_conversation(
    tenant_id: str,
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ConversationResponse:
    conv = await svc.create_conversation(
        tenant_id=tenant_id,
        user_id=user.sub,
        title=body.title,
        provider=body.provider.value,
        model=body.model,
        system_prompt=body.system_prompt,
    )
    return ConversationResponse.model_validate(conv)


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List chat conversations",
)
@require_tenant_access
async def list_conversations(
    tenant_id: str,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Filter by status: active or archived"),
) -> ConversationListResponse:
    items, total = await svc.list_conversations(
        tenant_id=tenant_id,
        user_id=user.sub,
        limit=limit,
        offset=offset,
        status=status,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get a chat conversation with messages",
)
@require_tenant_access
async def get_conversation(
    tenant_id: str,
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ConversationDetailResponse:
    conv = await svc.get_conversation(conversation_id, tenant_id, user.sub)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetailResponse.model_validate(conv)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Rename a chat conversation",
)
@require_tenant_access
async def update_conversation(
    tenant_id: str,
    conversation_id: UUID,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ConversationResponse:
    conv = await svc.update_conversation(conversation_id, tenant_id, user.sub, title=body.title)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conv)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete a chat conversation",
)
@require_tenant_access
async def delete_conversation(
    tenant_id: str,
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> None:
    deleted = await svc.delete_conversation(conversation_id, tenant_id, user.sub)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


# ---------------------------------------------------------------------------
# Archive / restore (CAB-289)
# ---------------------------------------------------------------------------


@router.patch(
    "/conversations/{conversation_id}/archive",
    response_model=ConversationResponse,
    summary="Archive or restore a chat conversation",
)
@require_tenant_access
async def archive_conversation(
    tenant_id: str,
    conversation_id: UUID,
    body: ConversationArchive,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ConversationResponse:
    conv = await svc.archive_conversation(conversation_id, tenant_id, user.sub, status=body.status.value)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conv)


# ---------------------------------------------------------------------------
# Tenant cascade delete (CAB-289)
# ---------------------------------------------------------------------------


@router.delete(
    "/conversations",
    status_code=200,
    summary="Delete ALL conversations for a tenant (admin)",
)
@require_tenant_access
async def delete_tenant_conversations(
    tenant_id: str,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> dict:
    count = await svc.delete_tenant_conversations(tenant_id)
    return {"deleted": count}


# ---------------------------------------------------------------------------
# GDPR retention purge (CAB-289)
# ---------------------------------------------------------------------------


@router.delete(
    "/conversations/purge",
    status_code=200,
    summary="Purge archived conversations older than retention period (GDPR)",
)
@require_tenant_access
async def purge_conversations(
    tenant_id: str,
    retention_days: int = Query(90, ge=1, le=3650),
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> dict:
    count = await svc.purge_expired_conversations(tenant_id, retention_days=retention_days)
    return {"purged": count}


# ---------------------------------------------------------------------------
# Message streaming
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message and stream the assistant reply (SSE)",
)
@require_tenant_access
async def send_message(
    tenant_id: str,
    conversation_id: UUID,
    body: MessageSend,
    request: Request,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> EventSourceResponse:
    api_key = request.headers.get("X-Provider-Api-Key", "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Provider-Api-Key header",
        )

    async def event_generator():  # type: ignore[return]
        async for event in svc.send_message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user.sub,
            content=body.content,
            api_key=api_key,
        ):
            if await request.is_disconnected():
                break
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(event.get("data", {})),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Usage statistics
# ---------------------------------------------------------------------------


@router.get(
    "/usage",
    response_model=ChatUsageResponse,
    summary="Get token usage for current user",
)
@require_tenant_access
async def get_usage(
    tenant_id: str,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ChatUsageResponse:
    stats = await svc.get_user_usage(tenant_id, user.sub)
    return ChatUsageResponse(**stats)


@router.get(
    "/usage/tenant",
    response_model=ChatTenantUsageResponse,
    summary="Get token usage for entire tenant (admin)",
)
@require_tenant_access
async def get_tenant_usage(
    tenant_id: str,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
) -> ChatTenantUsageResponse:
    stats = await svc.get_tenant_usage(tenant_id)
    return ChatTenantUsageResponse(**stats)


# ---------------------------------------------------------------------------
# Token metering (CAB-288)
# ---------------------------------------------------------------------------


@router.get(
    "/usage/budget",
    response_model=TokenBudgetStatusResponse,
    summary="Get token budget status for current user",
)
@require_tenant_access
async def get_budget_status(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenBudgetStatusResponse:
    repo = ChatTokenUsageRepository(db)
    budget = settings.CHAT_TOKEN_BUDGET_DAILY or 1_000_000
    status = await repo.get_budget_status(tenant_id, user.sub, daily_budget=budget)
    return TokenBudgetStatusResponse(**status)


@router.get(
    "/usage/metering",
    response_model=TokenUsageStatsResponse,
    summary="Get aggregated token usage statistics (admin)",
)
@require_tenant_access
async def get_usage_stats(
    tenant_id: str,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenUsageStatsResponse:
    repo = ChatTokenUsageRepository(db)
    stats = await repo.get_usage_stats(tenant_id, days=days)
    return TokenUsageStatsResponse(**stats)
