# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Repository for MCP Server subscription CRUD operations.

Reference: PLAN-MCP-SUBSCRIPTIONS.md
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from src.models.mcp_subscription import (
    MCPServer,
    MCPServerTool,
    MCPServerSubscription,
    MCPToolAccess,
    MCPServerCategory,
    MCPServerStatus,
    MCPSubscriptionStatus,
    MCPToolAccessStatus,
)


class MCPServerRepository:
    """Repository for MCP Server database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, server: MCPServer) -> MCPServer:
        """Create a new MCP Server."""
        self.session.add(server)
        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def get_by_id(self, server_id: UUID) -> Optional[MCPServer]:
        """Get server by ID with tools."""
        result = await self.session.execute(
            select(MCPServer)
            .options(selectinload(MCPServer.tools))
            .where(MCPServer.id == server_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[MCPServer]:
        """Get server by name."""
        result = await self.session.execute(
            select(MCPServer)
            .options(selectinload(MCPServer.tools))
            .where(MCPServer.name == name)
        )
        return result.scalar_one_or_none()

    async def list_visible_for_user(
        self,
        user_roles: List[str],
        tenant_id: Optional[str] = None,
        category: Optional[MCPServerCategory] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPServer], int]:
        """List servers visible to a user based on roles and visibility config."""
        query = select(MCPServer).options(selectinload(MCPServer.tools))

        # Filter by status (only active)
        query = query.where(MCPServer.status == MCPServerStatus.ACTIVE)

        # Filter by category if provided
        if category:
            query = query.where(MCPServer.category == category)

        # Filter by tenant if provided (for tenant-specific servers)
        if tenant_id:
            query = query.where(
                or_(
                    MCPServer.tenant_id.is_(None),  # Public servers
                    MCPServer.tenant_id == tenant_id,  # Tenant's own servers
                )
            )

        # TODO: Add visibility filtering based on user_roles and server.visibility JSON
        # This requires JSON querying which varies by database

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(MCPServer.display_name)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        servers = result.scalars().all()

        return list(servers), total

    async def list_all(
        self,
        category: Optional[MCPServerCategory] = None,
        status: Optional[MCPServerStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPServer], int]:
        """List all servers (admin only)."""
        query = select(MCPServer).options(selectinload(MCPServer.tools))

        if category:
            query = query.where(MCPServer.category == category)
        if status:
            query = query.where(MCPServer.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(MCPServer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        servers = result.scalars().all()

        return list(servers), total

    async def update(self, server: MCPServer) -> MCPServer:
        """Update a server."""
        server.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def delete(self, server: MCPServer) -> None:
        """Delete a server."""
        await self.session.delete(server)
        await self.session.flush()


class MCPSubscriptionRepository:
    """Repository for MCP subscription database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, subscription: MCPServerSubscription) -> MCPServerSubscription:
        """Create a new subscription."""
        self.session.add(subscription)
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_by_id(self, subscription_id: UUID) -> Optional[MCPServerSubscription]:
        """Get subscription by ID with server and tool access."""
        result = await self.session.execute(
            select(MCPServerSubscription)
            .options(
                selectinload(MCPServerSubscription.server).selectinload(MCPServer.tools),
                selectinload(MCPServerSubscription.tool_access),
            )
            .where(MCPServerSubscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_key_hash(self, api_key_hash: str) -> Optional[MCPServerSubscription]:
        """Get subscription by API key hash (for validation)."""
        result = await self.session.execute(
            select(MCPServerSubscription)
            .options(
                selectinload(MCPServerSubscription.server),
                selectinload(MCPServerSubscription.tool_access),
            )
            .where(MCPServerSubscription.api_key_hash == api_key_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_previous_key_hash(self, api_key_hash: str) -> Optional[MCPServerSubscription]:
        """Get subscription by previous API key hash (grace period validation)."""
        now = datetime.utcnow()
        result = await self.session.execute(
            select(MCPServerSubscription)
            .options(
                selectinload(MCPServerSubscription.server),
                selectinload(MCPServerSubscription.tool_access),
            )
            .where(
                and_(
                    MCPServerSubscription.previous_api_key_hash == api_key_hash,
                    MCPServerSubscription.previous_key_expires_at > now
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_subscriber_and_server(
        self,
        subscriber_id: str,
        server_id: UUID,
    ) -> Optional[MCPServerSubscription]:
        """Check if subscription already exists for subscriber+server combo."""
        result = await self.session.execute(
            select(MCPServerSubscription)
            .options(selectinload(MCPServerSubscription.tool_access))
            .where(
                and_(
                    MCPServerSubscription.subscriber_id == subscriber_id,
                    MCPServerSubscription.server_id == server_id,
                    MCPServerSubscription.status.in_([
                        MCPSubscriptionStatus.PENDING,
                        MCPSubscriptionStatus.ACTIVE
                    ])
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_subscriber(
        self,
        subscriber_id: str,
        status: Optional[MCPSubscriptionStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPServerSubscription], int]:
        """List subscriptions for a subscriber."""
        query = select(MCPServerSubscription).options(
            selectinload(MCPServerSubscription.server).selectinload(MCPServer.tools),
            selectinload(MCPServerSubscription.tool_access),
        ).where(MCPServerSubscription.subscriber_id == subscriber_id)

        if status:
            query = query.where(MCPServerSubscription.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(MCPServerSubscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: Optional[MCPSubscriptionStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPServerSubscription], int]:
        """List subscriptions for a tenant."""
        query = select(MCPServerSubscription).options(
            selectinload(MCPServerSubscription.server),
            selectinload(MCPServerSubscription.tool_access),
        ).where(MCPServerSubscription.tenant_id == tenant_id)

        if status:
            query = query.where(MCPServerSubscription.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(MCPServerSubscription.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def list_pending(
        self,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPServerSubscription], int]:
        """List pending subscriptions for approval."""
        query = select(MCPServerSubscription).options(
            selectinload(MCPServerSubscription.server),
            selectinload(MCPServerSubscription.tool_access),
        ).where(MCPServerSubscription.status == MCPSubscriptionStatus.PENDING)

        if tenant_id:
            query = query.where(MCPServerSubscription.tenant_id == tenant_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate (oldest first for approvals)
        query = query.order_by(MCPServerSubscription.created_at.asc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        subscriptions = result.scalars().all()

        return list(subscriptions), total

    async def update_status(
        self,
        subscription: MCPServerSubscription,
        new_status: MCPSubscriptionStatus,
        reason: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> MCPServerSubscription:
        """Update subscription status."""
        subscription.status = new_status
        subscription.updated_at = datetime.utcnow()

        if reason:
            subscription.status_reason = reason

        if new_status == MCPSubscriptionStatus.ACTIVE:
            subscription.approved_at = datetime.utcnow()
            subscription.approved_by = actor_id
        elif new_status == MCPSubscriptionStatus.REVOKED:
            subscription.revoked_at = datetime.utcnow()
            subscription.revoked_by = actor_id

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def set_api_key(
        self,
        subscription: MCPServerSubscription,
        api_key_hash: str,
        api_key_prefix: str,
        vault_path: Optional[str] = None,
    ) -> MCPServerSubscription:
        """Set API key for subscription (after approval)."""
        subscription.api_key_hash = api_key_hash
        subscription.api_key_prefix = api_key_prefix
        subscription.vault_path = vault_path
        subscription.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def rotate_key(
        self,
        subscription: MCPServerSubscription,
        new_api_key_hash: str,
        new_api_key_prefix: str,
        grace_period_hours: int = 24,
    ) -> MCPServerSubscription:
        """Rotate API key with grace period."""
        now = datetime.utcnow()

        # Store current key as previous for grace period
        subscription.previous_api_key_hash = subscription.api_key_hash
        subscription.previous_key_expires_at = now + timedelta(hours=grace_period_hours)

        # Set new key
        subscription.api_key_hash = new_api_key_hash
        subscription.api_key_prefix = new_api_key_prefix
        subscription.last_rotated_at = now
        subscription.rotation_count = (subscription.rotation_count or 0) + 1
        subscription.updated_at = now

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def update_usage(
        self,
        subscription: MCPServerSubscription,
    ) -> MCPServerSubscription:
        """Update usage tracking."""
        subscription.usage_count = (subscription.usage_count or 0) + 1
        subscription.last_used_at = datetime.utcnow()
        await self.session.flush()
        return subscription

    async def set_expiration(
        self,
        subscription: MCPServerSubscription,
        expires_at: Optional[datetime],
    ) -> MCPServerSubscription:
        """Set subscription expiration date."""
        subscription.expires_at = expires_at
        subscription.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def get_stats(self, tenant_id: Optional[str] = None) -> dict:
        """Get subscription statistics.

        Optimized to use GROUP BY instead of N+1 queries for status counts.
        """
        # Build base filter condition
        base_conditions = []
        if tenant_id:
            base_conditions.append(MCPServerSubscription.tenant_id == tenant_id)

        # Total count - single query
        total_query = select(func.count(MCPServerSubscription.id))
        if base_conditions:
            total_query = total_query.where(and_(*base_conditions))
        total_result = await self.session.execute(total_query)
        total = total_result.scalar_one()

        # Count by status - single query with GROUP BY instead of N+1
        status_query = select(
            MCPServerSubscription.status,
            func.count(MCPServerSubscription.id)
        ).group_by(MCPServerSubscription.status)
        if base_conditions:
            status_query = status_query.where(and_(*base_conditions))
        status_result = await self.session.execute(status_query)

        # Initialize all statuses to 0, then update with actual counts
        by_status = {status.value: 0 for status in MCPSubscriptionStatus}
        for row in status_result:
            by_status[row[0].value] = row[1]

        # Recent 24h - single query
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_conditions = [MCPServerSubscription.created_at >= yesterday]
        if tenant_id:
            recent_conditions.append(MCPServerSubscription.tenant_id == tenant_id)
        recent_query = select(func.count(MCPServerSubscription.id)).where(and_(*recent_conditions))
        recent_result = await self.session.execute(recent_query)
        recent_24h = recent_result.scalar_one()

        # Count by server - single query with JOIN and GROUP BY
        by_server = {}
        server_query = (
            select(MCPServer.name, func.count(MCPServerSubscription.id))
            .join(MCPServerSubscription, MCPServer.id == MCPServerSubscription.server_id)
            .group_by(MCPServer.name)
        )
        if tenant_id:
            server_query = server_query.where(MCPServerSubscription.tenant_id == tenant_id)
        server_result = await self.session.execute(server_query)
        for row in server_result:
            by_server[row[0]] = row[1]

        return {
            "total_subscriptions": total,
            "by_status": by_status,
            "by_server": by_server,
            "recent_24h": recent_24h,
        }


class MCPToolAccessRepository:
    """Repository for tool access operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tool_access: MCPToolAccess) -> MCPToolAccess:
        """Create a new tool access record."""
        self.session.add(tool_access)
        await self.session.flush()
        await self.session.refresh(tool_access)
        return tool_access

    async def create_many(self, tool_accesses: List[MCPToolAccess]) -> List[MCPToolAccess]:
        """Create multiple tool access records."""
        self.session.add_all(tool_accesses)
        await self.session.flush()
        return tool_accesses

    async def get_by_subscription_and_tool(
        self,
        subscription_id: UUID,
        tool_id: UUID,
    ) -> Optional[MCPToolAccess]:
        """Get tool access by subscription and tool."""
        result = await self.session.execute(
            select(MCPToolAccess).where(
                and_(
                    MCPToolAccess.subscription_id == subscription_id,
                    MCPToolAccess.tool_id == tool_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_subscription(
        self,
        subscription_id: UUID,
    ) -> List[MCPToolAccess]:
        """List all tool access records for a subscription."""
        result = await self.session.execute(
            select(MCPToolAccess).where(
                MCPToolAccess.subscription_id == subscription_id
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        tool_access: MCPToolAccess,
        status: MCPToolAccessStatus,
        actor_id: Optional[str] = None,
    ) -> MCPToolAccess:
        """Update tool access status."""
        tool_access.status = status
        if status == MCPToolAccessStatus.ENABLED and actor_id:
            tool_access.granted_at = datetime.utcnow()
            tool_access.granted_by = actor_id
        await self.session.flush()
        await self.session.refresh(tool_access)
        return tool_access

    async def update_usage(
        self,
        tool_access: MCPToolAccess,
    ) -> MCPToolAccess:
        """Update usage tracking for a tool."""
        tool_access.usage_count = (tool_access.usage_count or 0) + 1
        tool_access.last_used_at = datetime.utcnow()
        await self.session.flush()
        return tool_access
