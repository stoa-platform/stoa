# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Welcome endpoint for invite token validation."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import settings
from control_plane.database import get_db
from control_plane.models.prospect_event import EventType
from control_plane.services import event_service, invite_service

router = APIRouter(tags=["welcome"])


@router.get(
    "/welcome/{token}",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Validate invite and redirect to portal",
    description="Validates the invite token and redirects to the onboarding portal.",
    responses={
        302: {"description": "Redirect to portal onboarding page"},
        404: {"description": "Token not found"},
        410: {"description": "Token has expired"},
    },
)
async def welcome(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Validate invite token and redirect to portal.

    Flow:
    1. Look up invite by token
    2. Check if token exists and hasn't expired
    3. Mark invite as opened (if first time)
    4. Record invite_opened event
    5. 302 redirect to portal with token

    Args:
        token: Invite token from URL
        db: Database session

    Returns:
        302 redirect to portal.gostoa.dev/onboarding?token={token}

    Raises:
        HTTPException: 404 if token not found, 410 if expired
    """
    # Look up invite
    invite = await invite_service.get_invite_by_token(db, token)

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite_not_found", "message": "Invalid invite token"},
        )

    # Check expiration
    if invite.is_expired:
        # Mark as expired if not already
        await invite_service.mark_invite_converted(db, invite)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "invite_expired", "message": "This invite link has expired"},
        )

    # Mark as opened (idempotent - only updates if still pending)
    await invite_service.mark_invite_opened(db, invite)

    # Record invite_opened event (always record for analytics)
    await event_service.record_event_simple(
        db,
        invite_id=invite.id,
        event_type=EventType.INVITE_OPENED,
        metadata={"token": token},
    )

    # Build redirect URL
    redirect_url = f"{settings.portal_url}/onboarding?token={token}"

    # Create redirect response with custom header
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    response.headers["X-Invite-Id"] = str(invite.id)

    return response
