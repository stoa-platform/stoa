"""Invite service with business logic."""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import settings
from control_plane.models.invite import Invite, InviteStatus
from control_plane.schemas.invite import InviteCreate


def generate_invite_token() -> str:
    """Generate a cryptographically secure invite token.

    Uses secrets.token_urlsafe(32) which provides 256 bits of entropy.
    The resulting token is 43 characters (URL-safe base64).
    """
    return secrets.token_urlsafe(32)


def build_invite_link(token: str) -> str:
    """Build the full invite URL."""
    return f"{settings.invite_base_url}/welcome/{token}"


def hash_invite_token(token: str) -> str:
    """SHA-256 hex digest of an invite token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_invite(
    db: AsyncSession,
    invite_data: InviteCreate,
    tenant_id: str,
) -> tuple[Invite, str]:
    """Create a new invite.

    The plaintext token is returned to the caller and is not stored.

    Args:
        db: Database session
        invite_data: Invite creation data
        tenant_id: Tenant that owns the invite

    Returns:
        Created invite and the one-time plaintext token
    """
    token = generate_invite_token()
    invite = Invite(
        email=invite_data.email,
        company=invite_data.company,
        tenant_id=tenant_id,
        source=invite_data.source,
        token_hash=hash_invite_token(token),
        status=InviteStatus.PENDING.value,
        expires_at=Invite.calculate_expires_at(),
    )

    db.add(invite)
    await db.flush()
    await db.refresh(invite)

    return invite, token


async def get_invite_by_id(db: AsyncSession, invite_id: UUID) -> Invite | None:
    """Get an invite by ID.

    Args:
        db: Database session
        invite_id: UUID of the invite

    Returns:
        Invite instance or None if not found
    """
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    return result.scalar_one_or_none()


async def get_invite_by_token(db: AsyncSession, token: str) -> Invite | None:
    """Get an invite by token.

    Args:
        db: Database session
        token: Invite token

    Returns:
        Invite instance or None if not found
    """
    result = await db.execute(
        select(Invite).where(Invite.token_hash == hash_invite_token(token))
    )
    return result.scalar_one_or_none()


async def list_invites(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: InviteStatus | None = None,
    tenant_id: str | None = None,
) -> tuple[list[Invite], int]:
    """List invites with optional filtering.

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        status: Optional status filter
        tenant_id: When set, restrict the list to this tenant

    Returns:
        Tuple of (invites, total_count)
    """
    query = select(Invite)
    count_query = select(Invite.id)

    if status:
        query = query.where(Invite.status == status.value)
        count_query = count_query.where(Invite.status == status.value)
    if tenant_id is not None:
        query = query.where(Invite.tenant_id == tenant_id)
        count_query = count_query.where(Invite.tenant_id == tenant_id)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Get paginated results
    query = query.order_by(Invite.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    invites = list(result.scalars().all())

    return invites, total


async def mark_invite_opened(db: AsyncSession, invite: Invite) -> Invite:
    """Mark an invite as opened.

    Only marks as opened if currently pending (idempotent for already opened).

    Args:
        db: Database session
        invite: Invite to mark as opened

    Returns:
        Updated invite instance
    """
    if invite.status == InviteStatus.PENDING.value:
        invite.mark_opened()
        await db.flush()
        await db.refresh(invite)

    return invite


async def mark_invite_converted(db: AsyncSession, invite: Invite) -> Invite:
    """Mark an invite as converted (sandbox created).

    Args:
        db: Database session
        invite: Invite to mark as converted

    Returns:
        Updated invite instance
    """
    if invite.status in (InviteStatus.PENDING.value, InviteStatus.OPENED.value):
        invite.mark_converted()
        await db.flush()
        await db.refresh(invite)

    return invite
