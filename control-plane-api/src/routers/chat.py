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
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..auth import User, get_current_user, require_tenant_access
from ..auth.rbac import require_role
from ..config import settings
from ..database import get_db
from ..repositories.chat_token_usage_repository import ChatTokenUsageRepository
from ..schemas.chat import (
    ChatSource,
    ChatTenantUsageResponse,
    ChatUsageResponse,
    ConversationArchive,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageSend,
    ModelDistributionResponse,
    ProviderKeySet,
    TenantChatSettings,
    TokenBudgetStatusResponse,
    TokenUsageStatsResponse,
)
from ..services.audit_service import AuditService
from ..services.chat_rate_limiter import check_rate_limit, record_event
from ..services.chat_security import compute_session_fingerprint
from ..services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/chat",
    tags=["Chat"],
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _check_kill_switch() -> None:
    """Raise 503 if the chat kill switch is enabled (CAB-1655)."""
    if settings.CHAT_KILL_SWITCH:
        raise HTTPException(
            status_code=503,
            detail="Chat is temporarily disabled",
        )


def _service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)


async def _resolve_source(request: Request) -> ChatSource:
    """Read X-Chat-Source header, default to console."""
    raw = request.headers.get("X-Chat-Source", "console").lower()
    if raw == "portal":
        return ChatSource.PORTAL
    return ChatSource.CONSOLE


async def _get_tenant_chat_settings(tenant_id: str, db: AsyncSession) -> TenantChatSettings:
    """Read chat settings from tenant.settings JSON column."""
    from ..models.tenant import Tenant

    q = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await db.execute(q)).scalar_one_or_none()
    if tenant is None:
        return TenantChatSettings()
    s = tenant.settings or {}
    return TenantChatSettings(
        chat_console_enabled=s.get("chat_console_enabled", True),
        chat_portal_enabled=s.get("chat_portal_enabled", True),
        chat_daily_budget=s.get("chat_daily_budget", 100_000),
    )


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    summary="Create a chat conversation",
    dependencies=[Depends(_check_kill_switch)],
)
@require_tenant_access
async def create_conversation(
    tenant_id: str,
    body: ConversationCreate,
    request: Request,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("User-Agent", "")
    fingerprint = compute_session_fingerprint(ip, user_agent) if ip else None
    conv = await svc.create_conversation(
        tenant_id=tenant_id,
        user_id=user.id,
        title=body.title,
        provider=body.provider.value,
        model=body.model,
        system_prompt=body.system_prompt,
        session_fingerprint=fingerprint,
    )
    audit = AuditService(db)
    await audit.record_event(
        tenant_id=tenant_id,
        action="chat_conversation_create",
        method="POST",
        path=f"/v1/tenants/{tenant_id}/chat/conversations",
        resource_type="chat_conversation",
        resource_id=str(conv.id),
        actor_id=user.id,
        client_ip=ip or None,
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
        user_id=user.id,
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
    conv = await svc.get_conversation(conversation_id, tenant_id, user.id)
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
    conv = await svc.update_conversation(conversation_id, tenant_id, user.id, title=body.title)
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
    request: Request,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await svc.delete_conversation(conversation_id, tenant_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ip = request.client.host if request.client else None
    audit = AuditService(db)
    await audit.record_event(
        tenant_id=tenant_id,
        action="chat_conversation_delete",
        method="DELETE",
        path=f"/v1/tenants/{tenant_id}/chat/conversations/{conversation_id}",
        resource_type="chat_conversation",
        resource_id=str(conversation_id),
        actor_id=user.id,
        client_ip=ip,
    )


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
    conv = await svc.archive_conversation(conversation_id, tenant_id, user.id, status=body.status.value)
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
    request: Request,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count = await svc.delete_tenant_conversations(tenant_id)
    ip = request.client.host if request.client else None
    audit = AuditService(db)
    await audit.record_event(
        tenant_id=tenant_id,
        action="chat_conversation_delete",
        method="DELETE",
        path=f"/v1/tenants/{tenant_id}/chat/conversations",
        resource_type="chat_conversation",
        actor_id=user.id,
        client_ip=ip,
        details={"cascade": True, "count": count},
    )
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
    request: Request,
    retention_days: int = Query(90, ge=1, le=3650),
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count = await svc.purge_expired_conversations(tenant_id, retention_days=retention_days)
    ip = request.client.host if request.client else None
    audit = AuditService(db)
    await audit.record_event(
        tenant_id=tenant_id,
        action="chat_conversation_purge",
        method="DELETE",
        path=f"/v1/tenants/{tenant_id}/chat/conversations/purge",
        resource_type="chat_conversation",
        actor_id=user.id,
        client_ip=ip,
        details={"retention_days": retention_days, "purged_count": count},
    )
    return {"purged": count}


# ---------------------------------------------------------------------------
# Message streaming
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message and stream the assistant reply (SSE)",
    dependencies=[Depends(_check_kill_switch)],
)
@require_tenant_access
async def send_message(
    tenant_id: str,
    conversation_id: UUID,
    body: MessageSend,
    request: Request,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(_service),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    # Resolve source from header (CAB-1851)
    source = await _resolve_source(request)

    # Check tenant chat settings — is chat enabled for this source? (CAB-1851)
    chat_settings = await _get_tenant_chat_settings(tenant_id, db)
    if source == ChatSource.CONSOLE and not chat_settings.chat_console_enabled:
        raise HTTPException(status_code=403, detail="Chat is disabled for this application")
    if source == ChatSource.PORTAL and not chat_settings.chat_portal_enabled:
        raise HTTPException(status_code=403, detail="Chat is disabled for this application")

    # Rate limit check (CAB-1655)
    allowed, reason, retry_after = check_rate_limit(user.id, tenant_id, "message")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=reason,
            headers={"Retry-After": str(retry_after)},
        )
    record_event(user.id, tenant_id, "message")

    # Provider selection: gateway mode (CAB-1822) vs direct Anthropic
    use_gateway = bool(settings.CHAT_GATEWAY_URL and settings.CHAT_GATEWAY_API_KEY)

    if use_gateway:
        # Gateway handles Anthropic API key injection — use STOA consumer key for auth
        api_key = settings.CHAT_GATEWAY_API_KEY
    else:
        # Direct mode: resolve Anthropic API key from header → tenant → global config
        api_key = request.headers.get("X-Provider-Api-Key", "")
        if not api_key:
            api_key = await svc.get_tenant_api_key(tenant_id) or ""
        if not api_key:
            api_key = settings.CHAT_PROVIDER_API_KEY
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="No API key: set X-Provider-Api-Key header or configure tenant key via PUT /provider-key",
            )

    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("User-Agent", "")
    fingerprint = compute_session_fingerprint(ip, user_agent) if ip else None

    async def event_generator():  # type: ignore[return]
        # Handle tool confirmation flow (CAB-1816 Phase 2)
        if body.tool_confirmation:
            tc = body.tool_confirmation
            async for event in svc.execute_confirmed_tool(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user.id,
                tool_name=tc.tool_name,
                tool_input=tc.tool_input,
                approved=tc.approved,
                user_roles=user.roles,
                client_ip=ip or None,
            ):
                if await request.is_disconnected():
                    break
                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(event.get("data", {})),
                }
            return

        async for event in svc.send_message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user.id,
            content=body.content,
            api_key=api_key,
            user_roles=user.roles,
            session_fingerprint=fingerprint,
            client_ip=ip or None,
            source=source.value,
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
    stats = await svc.get_user_usage(tenant_id, user.id)
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
    status = await repo.get_budget_status(tenant_id, user.id, daily_budget=budget)
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
    group_by: str | None = Query(None, description="Group breakdown by 'source' for per-app stats"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenUsageStatsResponse:
    repo = ChatTokenUsageRepository(db)
    stats = await repo.get_usage_stats(tenant_id, days=days, group_by_source=group_by == "source")
    return TokenUsageStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Model distribution (CAB-1868)
# ---------------------------------------------------------------------------


@router.get(
    "/usage/models",
    response_model=ModelDistributionResponse,
    summary="Get model usage distribution across conversations (admin)",
)
@require_tenant_access
async def get_model_distribution(
    tenant_id: str,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    svc: ChatService = Depends(_service),
) -> ModelDistributionResponse:
    models = await svc.get_model_distribution(tenant_id)
    total = sum(m["conversations"] for m in models)
    return ModelDistributionResponse(models=models, total_conversations=total)


# ---------------------------------------------------------------------------
# Chat audit trail (CAB-1654)
# ---------------------------------------------------------------------------


class ChatAuditEntry(BaseModel):
    """A chat audit log entry."""

    id: str
    timestamp: datetime
    action: str
    resource_type: str
    resource_id: str | None
    resource_name: str | None
    outcome: str
    actor_id: str | None
    client_ip: str | None
    details: dict | None


class ChatAuditListResponse(BaseModel):
    """Paginated chat audit list."""

    entries: list[ChatAuditEntry]
    total: int
    page: int
    page_size: int


@router.get(
    "/audit",
    response_model=ChatAuditListResponse,
    summary="Query chat audit events (admin only)",
)
@require_tenant_access
async def list_chat_audit(
    tenant_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, description="Filter by action (e.g. chat_tool_call)"),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> ChatAuditListResponse:
    audit_svc = AuditService(db)
    # Filter to chat-related resource types only
    events, total = await audit_svc.list_events(
        tenant_id,
        page=page,
        page_size=per_page,
        action=action,
        resource_type=None,
        start_date=start_date,
        end_date=end_date,
        search="chat_",
    )
    entries = [
        ChatAuditEntry(
            id=e.id,
            timestamp=e.created_at,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            resource_name=e.resource_name,
            outcome=e.outcome,
            actor_id=e.actor_id,
            client_ip=e.client_ip,
            details=e.details,
        )
        for e in events
        if e.action.startswith("chat_") or e.resource_type.startswith("chat_")
    ]
    return ChatAuditListResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=per_page,
    )


# ---------------------------------------------------------------------------
# Tenant chat settings (CAB-1851)
# ---------------------------------------------------------------------------


@router.get(
    "/settings",
    response_model=TenantChatSettings,
    summary="Get tenant chat settings",
)
@require_tenant_access
async def get_chat_settings(
    tenant_id: str,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> TenantChatSettings:
    return await _get_tenant_chat_settings(tenant_id, db)


@router.put(
    "/settings",
    response_model=TenantChatSettings,
    summary="Update tenant chat settings",
)
@require_tenant_access
async def update_chat_settings(
    tenant_id: str,
    body: TenantChatSettings,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> TenantChatSettings:
    from ..models.tenant import Tenant

    q = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await db.execute(q)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    s = dict(tenant.settings or {})
    s["chat_console_enabled"] = body.chat_console_enabled
    s["chat_portal_enabled"] = body.chat_portal_enabled
    s["chat_daily_budget"] = body.chat_daily_budget
    tenant.settings = s
    await db.flush()
    return body


# ---------------------------------------------------------------------------
# Provider key management (admin)
# ---------------------------------------------------------------------------


@router.put(
    "/provider-key",
    status_code=204,
    summary="Set the tenant-level chat provider API key (admin)",
)
@require_tenant_access
async def set_provider_key(
    tenant_id: str,
    body: ProviderKeySet,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    svc: ChatService = Depends(_service),
) -> None:
    ok = await svc.set_tenant_api_key(tenant_id, body.api_key)
    if not ok:
        raise HTTPException(status_code=404, detail="Tenant not found")
