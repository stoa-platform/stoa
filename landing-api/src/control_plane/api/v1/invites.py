"""Invite API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import settings
from control_plane.database import get_db
from control_plane.models.invite import InviteStatus
from control_plane.schemas.invite import InviteCreate, InviteListResponse, InviteResponse
from control_plane.schemas.metrics import MetricsResponse
from control_plane.services import invite_service, metrics_service

router = APIRouter(prefix="/invites", tags=["invites"])

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


def _build_response(invite) -> InviteResponse:
    """Build InviteResponse from Invite model."""
    return InviteResponse(
        id=invite.id,
        email=invite.email,
        company=invite.company,
        token=invite.token,
        source=invite.source,
        status=InviteStatus(invite.status),
        invite_link=invite_service.build_invite_link(invite.token),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        opened_at=invite.opened_at,
    )


@router.post(
    "",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invite",
    description="Create a new prospect invite and return the invite link.",
)
@limiter.limit(settings.rate_limit_invites)
async def create_invite(
    request: Request,
    invite_data: InviteCreate,
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """Create a new invite.

    Rate limited to 10 requests per minute per IP address.

    Args:
        request: FastAPI request (required for rate limiter)
        invite_data: Invite creation data
        db: Database session

    Returns:
        Created invite with invite_link
    """
    invite = await invite_service.create_invite(db, invite_data)
    return _build_response(invite)


@router.get(
    "",
    response_model=InviteListResponse,
    summary="List invites",
    description="List all invites with optional status filtering.",
)
async def list_invites(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    status_filter: InviteStatus | None = Query(
        None,
        alias="status",
        description="Filter by status",
    ),
    db: AsyncSession = Depends(get_db),
) -> InviteListResponse:
    """List invites with optional filtering.

    Args:
        skip: Pagination offset
        limit: Maximum number of results
        status_filter: Optional status filter
        db: Database session

    Returns:
        List of invites with total count
    """
    invites, total = await invite_service.list_invites(
        db, skip=skip, limit=limit, status=status_filter
    )
    return InviteListResponse(
        invites=[_build_response(inv) for inv in invites],
        total=total,
    )


@router.get(
    "/{invite_id}",
    response_model=InviteResponse,
    summary="Get invite by ID",
    description="Get a single invite by its UUID.",
)
async def get_invite(
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """Get an invite by ID.

    Args:
        invite_id: UUID of the invite
        db: Database session

    Returns:
        Invite details

    Raises:
        HTTPException: 404 if invite not found
    """
    invite = await invite_service.get_invite_by_id(db, invite_id)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite_not_found", "message": "Invite not found"},
        )
    return _build_response(invite)


@router.get(
    "/{invite_id}/metrics",
    response_model=MetricsResponse,
    summary="Get invite metrics",
    description="Get calculated metrics for an invite including time-to-sandbox, time-to-first-tool, and event timeline.",
)
async def get_invite_metrics(
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> MetricsResponse:
    """Get calculated metrics for an invite.

    Returns:
    - time_to_sandbox: seconds from invite_opened to sandbox_created
    - time_to_first_tool: seconds from sandbox_created to first tool_called
    - Event counts by type
    - Full event timeline

    Args:
        invite_id: UUID of the invite
        db: Database session

    Returns:
        Calculated metrics with event timeline

    Raises:
        HTTPException: 404 if invite not found
    """
    invite = await invite_service.get_invite_by_id(db, invite_id)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite_not_found", "message": "Invite not found"},
        )

    return await metrics_service.calculate_metrics(db, invite)
