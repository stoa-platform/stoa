"""Repository for subscription CRUD operations"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from src.models.subscription import Subscription, SubscriptionStatus


class SubscriptionRepository:
    """Repository for subscription database operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, subscription: Subscription) -> Subscription:
        """Create a new subscription"""
        self.session.add(subscription)
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_by_id(self, subscription_id: UUID) -> Optional[Subscription]:
        """Get subscription by ID"""
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_key_hash(self, api_key_hash: str) -> Optional[Subscription]:
        """Get subscription by API key hash (for validation)"""
        result = await self.session.execute(
            select(Subscription).where(Subscription.api_key_hash == api_key_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_application_and_api(
        self,
        application_id: str,
        api_id: str
    ) -> Optional[Subscription]:
        """Check if subscription already exists for app+api combo"""
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.application_id == application_id,
                    Subscription.api_id == api_id,
                    Subscription.status.in_([
                        SubscriptionStatus.PENDING,
                        SubscriptionStatus.ACTIVE
                    ])
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_subscriber(
        self,
        subscriber_id: str,
        status: Optional[SubscriptionStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Subscription], int]:
        """List subscriptions for a subscriber with pagination"""
        query = select(Subscription).where(
            Subscription.subscriber_id == subscriber_id
        )

        if status:
            query = query.where(Subscription.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Subscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[SubscriptionStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Subscription], int]:
        """List subscriptions for a tenant with pagination"""
        query = select(Subscription).where(
            Subscription.tenant_id == tenant_id
        )

        if status:
            query = query.where(Subscription.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Subscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def list_by_api(
        self,
        api_id: str,
        tenant_id: str,
        status: Optional[SubscriptionStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Subscription], int]:
        """List subscriptions for an API with pagination"""
        query = select(Subscription).where(
            and_(
                Subscription.api_id == api_id,
                Subscription.tenant_id == tenant_id
            )
        )

        if status:
            query = query.where(Subscription.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Subscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def list_pending(
        self,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Subscription], int]:
        """List pending subscriptions for approval"""
        query = select(Subscription).where(
            Subscription.status == SubscriptionStatus.PENDING
        )

        if tenant_id:
            query = query.where(Subscription.tenant_id == tenant_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Subscription.created_at.asc())  # Oldest first
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def update_status(
        self,
        subscription: Subscription,
        new_status: SubscriptionStatus,
        reason: Optional[str] = None,
        actor_id: Optional[str] = None
    ) -> Subscription:
        """Update subscription status"""
        subscription.status = new_status
        subscription.updated_at = datetime.utcnow()

        if reason:
            subscription.status_reason = reason

        if new_status == SubscriptionStatus.ACTIVE:
            subscription.approved_at = datetime.utcnow()
            subscription.approved_by = actor_id
        elif new_status == SubscriptionStatus.REVOKED:
            subscription.revoked_at = datetime.utcnow()
            subscription.revoked_by = actor_id

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def set_expiration(
        self,
        subscription: Subscription,
        expires_at: Optional[datetime]
    ) -> Subscription:
        """Set subscription expiration date"""
        subscription.expires_at = expires_at
        subscription.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_stats(self, tenant_id: Optional[str] = None) -> dict:
        """Get subscription statistics"""
        base_query = select(Subscription)
        if tenant_id:
            base_query = base_query.where(Subscription.tenant_id == tenant_id)

        # Total count
        total_result = await self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = total_result.scalar_one()

        # Count by status
        by_status = {}
        for status in SubscriptionStatus:
            status_query = select(func.count()).where(
                Subscription.status == status
            )
            if tenant_id:
                status_query = status_query.where(Subscription.tenant_id == tenant_id)
            result = await self.session.execute(status_query)
            by_status[status.value] = result.scalar_one()

        # Recent 24h
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_query = select(func.count()).where(
            Subscription.created_at >= yesterday
        )
        if tenant_id:
            recent_query = recent_query.where(Subscription.tenant_id == tenant_id)
        recent_result = await self.session.execute(recent_query)
        recent_24h = recent_result.scalar_one()

        return {
            "total": total,
            "by_status": by_status,
            "recent_24h": recent_24h
        }

    async def delete(self, subscription: Subscription) -> None:
        """Delete a subscription (hard delete - use with caution)"""
        await self.session.delete(subscription)
        await self.session.flush()

    async def rotate_key(
        self,
        subscription: Subscription,
        new_api_key_hash: str,
        new_api_key_prefix: str,
        grace_period_hours: int = 24
    ) -> Subscription:
        """
        Rotate API key with grace period support.

        The old key is stored and remains valid for the specified grace period.
        After the grace period expires, only the new key is valid.
        """
        now = datetime.utcnow()

        # Store the current key as previous (for grace period)
        subscription.previous_api_key_hash = subscription.api_key_hash
        subscription.previous_key_expires_at = now + timedelta(hours=grace_period_hours)

        # Set the new key
        subscription.api_key_hash = new_api_key_hash
        subscription.api_key_prefix = new_api_key_prefix

        # Update rotation metadata
        subscription.last_rotated_at = now
        subscription.rotation_count = (subscription.rotation_count or 0) + 1
        subscription.updated_at = now

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_by_previous_key_hash(
        self,
        api_key_hash: str
    ) -> Optional[Subscription]:
        """
        Get subscription by previous API key hash (for grace period validation).

        Only returns subscriptions where the previous key is still within grace period.
        """
        now = datetime.utcnow()
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.previous_api_key_hash == api_key_hash,
                    Subscription.previous_key_expires_at > now
                )
            )
        )
        return result.scalar_one_or_none()

    async def cleanup_expired_previous_keys(self) -> int:
        """
        Clean up expired previous keys (remove grace period data after expiry).

        Returns the number of subscriptions cleaned up.
        """
        from sqlalchemy import update

        now = datetime.utcnow()
        result = await self.session.execute(
            update(Subscription)
            .where(
                and_(
                    Subscription.previous_key_expires_at.isnot(None),
                    Subscription.previous_key_expires_at < now
                )
            )
            .values(
                previous_api_key_hash=None,
                previous_key_expires_at=None
            )
        )
        await self.session.flush()
        return result.rowcount
