"""Public endpoint for portal email capture + admin access request management.

Public (no auth): POST /v1/access-requests — rate-limited, honeypot-protected
Admin (cpi-admin): GET /v1/admin/access-requests — paginated list
"""

import asyncio
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from src.auth.dependencies import User, get_current_user
from src.config import settings
from src.database import get_db
from src.middleware.rate_limit import limiter
from src.models.access_request import AccessRequest
from src.schemas.access_request import (
    AccessRequestCreate,
    AccessRequestDetail,
    AccessRequestListResponse,
    AccessRequestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/access-requests", tags=["Access Requests"])
admin_router = APIRouter(prefix="/v1/admin/access-requests", tags=["Admin Access Requests"])


# ---------------------------------------------------------------------------
# Slack notification (fire-and-forget)
# ---------------------------------------------------------------------------


async def _notify_slack_new_request(email: str, company: str | None, source: str | None) -> None:
    """Post a Slack notification for a new access request. Best-effort."""
    webhook_url = getattr(settings, "SLACK_WEBHOOK_URL", None) or ""
    if not webhook_url:
        return
    try:
        text = f":envelope: New enterprise access request from *{email}*"
        if company:
            text += f" ({company})"
        if source:
            text += f" via {source}"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook_url, json={"text": text})
    except Exception as exc:
        logger.warning("Failed to send Slack notification for access request: %s", exc)


# ---------------------------------------------------------------------------
# Public endpoint (no auth, rate-limited)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=AccessRequestResponse,
    responses={
        200: {"description": "Email already registered"},
        201: {"description": "New request created"},
    },
)
@limiter.limit("5/minute")
async def create_access_request(
    request: Request,
    payload: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Submit an access request (public, no auth, rate-limited 5/min per IP).

    Idempotent: returns 200 if email already exists, 201 if new.
    """
    # Honeypot: if invisible field is filled, silently fake success (bot trap)
    if payload.website:
        return JSONResponse(
            status_code=201,
            content=AccessRequestResponse(
                message="Thank you! We'll reach out shortly.",
                request_id=uuid.uuid4(),
            ).model_dump(mode="json"),
        )

    result = await db.execute(select(AccessRequest).where(AccessRequest.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing:
        return JSONResponse(
            status_code=200,
            content=AccessRequestResponse(
                message="Thank you! We'll reach out shortly.",
                request_id=existing.id,
            ).model_dump(mode="json"),
        )

    access_request = AccessRequest(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        company=payload.company,
        role=payload.role,
        source=payload.source,
    )
    db.add(access_request)
    await db.flush()

    # Fire-and-forget Slack notification
    asyncio.create_task(_notify_slack_new_request(payload.email, payload.company, payload.source))

    return JSONResponse(
        status_code=201,
        content=AccessRequestResponse(
            message="Thank you! We'll reach out shortly.",
            request_id=access_request.id,
        ).model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Admin endpoint (cpi-admin only)
# ---------------------------------------------------------------------------


def _require_admin(user: User) -> None:
    """Require cpi-admin role for access."""
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Platform admin access required")


@admin_router.get("", response_model=AccessRequestListResponse)
async def list_access_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="Filter by status (pending, contacted, converted)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
) -> AccessRequestListResponse:
    """List all access requests with pagination.

    **Requires**: `cpi-admin` role.
    """
    _require_admin(user)

    query = select(AccessRequest)
    count_query = select(func.count()).select_from(AccessRequest)

    if status:
        query = query.where(AccessRequest.status == status)
        count_query = count_query.where(AccessRequest.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(AccessRequest.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return AccessRequestListResponse(
        data=[AccessRequestDetail.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
    )
