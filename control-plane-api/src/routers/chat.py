"""Chat Agent router — conversation CRUD + SSE message streaming (CAB-286).

Provides 7 endpoints:
  POST   /v1/tenants/{tenant_id}/chat/conversations              — create
  GET    /v1/tenants/{tenant_id}/chat/conversations              — list
  GET    /v1/tenants/{tenant_id}/chat/conversations/{id}         — get (with messages)
  PATCH  /v1/tenants/{tenant_id}/chat/conversations/{id}         — rename
  POST   /v1/tenants/{tenant_id}/chat/conversations/{id}/messages — send + stream
  DELETE /v1/tenants/{tenant_id}/chat/conversations/{id}         — delete
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
from ..database import get_db
from ..schemas.chat import (
    ChatTenantUsageResponse,
    ChatUsageResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageSend,
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
) -> ConversationListResponse:
    items, total = await svc.list_conversations(
        tenant_id=tenant_id,
        user_id=user.sub,
        limit=limit,
        offset=offset,
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
