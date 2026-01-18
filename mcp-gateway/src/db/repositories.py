"""CAB-660: SQLAlchemy Repositories for Tool Handlers.

Repository pattern for database access using SQLAlchemy AsyncSession.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Tenant, User, API, APIEndpoint, Subscription, AuditLog, UACContract


# =============================================================================
# DATA TRANSFER OBJECTS
# =============================================================================


@dataclass
class TenantDTO:
    """Tenant data transfer object."""

    id: str
    name: str
    description: str | None = None
    status: str = "active"
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Computed fields
    api_count: int = 0
    subscription_count: int = 0


@dataclass
class APIDTO:
    """API data transfer object."""

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    status: str = "active"
    version: str | None = None
    owner_tenant_id: str | None = None
    access_type: str = "public"
    allowed_tenants: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    rate_limit: str | None = None
    spec: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass
class APIEndpointDTO:
    """API Endpoint data transfer object."""

    method: str
    path: str
    description: str | None = None


@dataclass
class SubscriptionDTO:
    """Subscription data transfer object."""

    id: str
    user_id: str
    tenant_id: str
    api_id: str
    plan: str = "free"
    status: str = "active"
    denial_reason: str | None = None
    created_at: datetime | None = None
    # Joined fields
    api_name: str | None = None
    user_name: str | None = None


@dataclass
class AuditLogDTO:
    """Audit log data transfer object."""

    id: int
    timestamp: datetime
    user_id: str | None
    tenant_id: str | None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    status: str | None = None
    details: dict[str, Any] | None = None
    ip_address: str | None = None


@dataclass
class UACContractDTO:
    """UAC Contract data transfer object."""

    id: str
    name: str
    description: str | None = None
    status: str = "active"
    terms: dict[str, Any] = field(default_factory=dict)
    tenant_ids: list[str] = field(default_factory=list)
    api_ids: list[str] = field(default_factory=list)


# =============================================================================
# BASE REPOSITORY
# =============================================================================


class BaseRepository:
    """Base class for all repositories."""

    def __init__(self, session: AsyncSession):
        self.session = session


# =============================================================================
# TENANT REPOSITORY
# =============================================================================


class TenantRepository(BaseRepository):
    """Repository for tenant operations."""

    async def get_by_id(self, tenant_id: str) -> TenantDTO | None:
        """Get tenant by ID with computed stats."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        dto = self._to_dto(tenant)
        stats = await self.get_stats(tenant_id)
        dto.api_count = stats["api_count"]
        dto.subscription_count = stats["subscription_count"]
        return dto

    async def list(self, include_inactive: bool = False) -> list[TenantDTO]:
        """List tenants with computed stats."""
        if include_inactive:
            result = await self.session.execute(
                select(Tenant).order_by(Tenant.name)
            )
        else:
            result = await self.session.execute(
                select(Tenant)
                .where(Tenant.status == "active")
                .order_by(Tenant.name)
            )

        tenants = []
        for tenant in result.scalars().all():
            dto = self._to_dto(tenant)
            stats = await self.get_stats(tenant.id)
            dto.api_count = stats["api_count"]
            dto.subscription_count = stats["subscription_count"]
            tenants.append(dto)

        return tenants

    async def get_stats(self, tenant_id: str) -> dict[str, int]:
        """Get tenant statistics."""
        api_count_result = await self.session.execute(
            select(func.count()).select_from(API).where(API.owner_tenant_id == tenant_id)
        )
        api_count = api_count_result.scalar() or 0

        sub_count_result = await self.session.execute(
            select(func.count())
            .select_from(Subscription)
            .where(
                and_(
                    Subscription.tenant_id == tenant_id,
                    Subscription.status == "active",
                )
            )
        )
        sub_count = sub_count_result.scalar() or 0

        return {"api_count": api_count, "subscription_count": sub_count}

    def _to_dto(self, tenant: Tenant) -> TenantDTO:
        return TenantDTO(
            id=tenant.id,
            name=tenant.name,
            description=tenant.description,
            status=tenant.status,
            settings=tenant.settings or {},
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
        )


# =============================================================================
# API REPOSITORY
# =============================================================================


class APIRepository(BaseRepository):
    """Repository for API catalog operations."""

    async def get_by_id(self, api_id: str) -> APIDTO | None:
        """Get API by ID."""
        result = await self.session.execute(
            select(API).where(API.id == api_id)
        )
        api = result.scalar_one_or_none()
        return self._to_dto(api) if api else None

    async def list(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[APIDTO], int]:
        """List APIs with tenant-aware filtering."""
        conditions = []

        if status:
            conditions.append(API.status == status)

        if category:
            conditions.append(API.category == category)

        # Tenant access filtering
        if tenant_id:
            conditions.append(
                or_(
                    API.access_type == "public",
                    API.owner_tenant_id == tenant_id,
                    API.allowed_tenants.contains([tenant_id]),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(API)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Get page
        offset = (page - 1) * page_size
        query = select(API).order_by(API.name).limit(page_size).offset(offset)
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        apis = [self._to_dto(api) for api in result.scalars().all()]

        return apis, total

    async def search(
        self,
        query: str,
        tenant_id: str | None = None,
        tags: list[str] | None = None,
    ) -> list[APIDTO]:
        """Full-text search on APIs."""
        search_pattern = f"%{query}%"

        conditions = [
            or_(
                API.name.ilike(search_pattern),
                API.description.ilike(search_pattern),
            )
        ]

        if tags:
            conditions.append(API.tags.overlap(tags))

        if tenant_id:
            conditions.append(
                or_(
                    API.access_type == "public",
                    API.owner_tenant_id == tenant_id,
                    API.allowed_tenants.contains([tenant_id]),
                )
            )

        result = await self.session.execute(
            select(API)
            .where(and_(*conditions))
            .order_by(API.name)
            .limit(50)
        )

        return [self._to_dto(api) for api in result.scalars().all()]

    async def get_endpoints(self, api_id: str) -> list[APIEndpointDTO]:
        """Get endpoints for an API."""
        result = await self.session.execute(
            select(APIEndpoint)
            .where(APIEndpoint.api_id == api_id)
            .order_by(APIEndpoint.path, APIEndpoint.method)
        )
        return [
            APIEndpointDTO(
                method=ep.method,
                path=ep.path,
                description=ep.description,
            )
            for ep in result.scalars().all()
        ]

    async def can_access(self, api_id: str, tenant_id: str) -> bool:
        """Check if tenant can access an API."""
        result = await self.session.execute(
            select(API.access_type, API.owner_tenant_id, API.allowed_tenants)
            .where(API.id == api_id)
        )
        row = result.one_or_none()
        if not row:
            return False

        access_type, owner, allowed = row

        if access_type == "public":
            return True
        if owner == tenant_id:
            return True
        if allowed and tenant_id in allowed:
            return True
        return False

    async def get_categories(self) -> list[dict[str, Any]]:
        """Get all categories with counts."""
        result = await self.session.execute(
            select(
                func.coalesce(API.category, "Uncategorized").label("category"),
                func.count().label("count"),
            )
            .where(API.status == "active")
            .group_by(API.category)
            .order_by(text("category"))
        )
        return [{"name": row.category, "count": row.count} for row in result.all()]

    def _to_dto(self, api: API) -> APIDTO:
        return APIDTO(
            id=api.id,
            name=api.name,
            description=api.description,
            category=api.category,
            status=api.status,
            version=api.version,
            owner_tenant_id=api.owner_tenant_id,
            access_type=api.access_type,
            allowed_tenants=list(api.allowed_tenants) if api.allowed_tenants else [],
            tags=list(api.tags) if api.tags else [],
            rate_limit=api.rate_limit,
            created_at=api.created_at,
        )


# =============================================================================
# SUBSCRIPTION REPOSITORY
# =============================================================================


class SubscriptionRepository(BaseRepository):
    """Repository for subscription operations."""

    async def get_by_id(self, sub_id: str, tenant_id: str) -> SubscriptionDTO | None:
        """Get subscription by ID with joined fields."""
        result = await self.session.execute(
            select(Subscription, API.name.label("api_name"), User.name.label("user_name"))
            .join(API, Subscription.api_id == API.id)
            .outerjoin(User, Subscription.user_id == User.id)
            .where(
                and_(
                    Subscription.id == sub_id,
                    Subscription.tenant_id == tenant_id,
                )
            )
        )
        row = result.one_or_none()
        if not row:
            return None

        sub, api_name, user_name = row
        return self._to_dto(sub, api_name, user_name)

    async def list(
        self,
        tenant_id: str,
        user_id: str | None = None,
        status: str | None = None,
        api_id: str | None = None,
    ) -> list[SubscriptionDTO]:
        """List subscriptions with filters."""
        conditions = [Subscription.tenant_id == tenant_id]

        if user_id:
            conditions.append(Subscription.user_id == user_id)
        if status:
            conditions.append(Subscription.status == status)
        if api_id:
            conditions.append(Subscription.api_id == api_id)

        result = await self.session.execute(
            select(Subscription, API.name.label("api_name"), User.name.label("user_name"))
            .join(API, Subscription.api_id == API.id)
            .outerjoin(User, Subscription.user_id == User.id)
            .where(and_(*conditions))
            .order_by(Subscription.created_at.desc())
        )

        return [
            self._to_dto(sub, api_name, user_name)
            for sub, api_name, user_name in result.all()
        ]

    async def create(
        self,
        sub_id: str,
        user_id: str,
        tenant_id: str,
        api_id: str,
        plan: str,
        api_key_hash: str,
    ) -> SubscriptionDTO | None:
        """Create a new subscription."""
        subscription = Subscription(
            id=sub_id,
            user_id=user_id,
            tenant_id=tenant_id,
            api_id=api_id,
            plan=plan,
            status="active",
            api_key_hash=api_key_hash,
        )
        self.session.add(subscription)
        await self.session.flush()
        return await self.get_by_id(sub_id, tenant_id)

    async def create_denied(
        self,
        sub_id: str,
        user_id: str,
        tenant_id: str,
        api_id: str,
        reason: str,
    ) -> None:
        """Create a denied subscription record."""
        subscription = Subscription(
            id=sub_id,
            user_id=user_id,
            tenant_id=tenant_id,
            api_id=api_id,
            status="denied",
            denial_reason=reason,
        )
        self.session.add(subscription)
        await self.session.flush()

    async def cancel(self, sub_id: str, tenant_id: str) -> bool:
        """Cancel a subscription."""
        result = await self.session.execute(
            select(Subscription).where(
                and_(
                    Subscription.id == sub_id,
                    Subscription.tenant_id == tenant_id,
                    Subscription.status == "active",
                )
            )
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return False

        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    def _to_dto(
        self,
        sub: Subscription,
        api_name: str | None = None,
        user_name: str | None = None,
    ) -> SubscriptionDTO:
        return SubscriptionDTO(
            id=sub.id,
            user_id=sub.user_id,
            tenant_id=sub.tenant_id,
            api_id=sub.api_id,
            plan=sub.plan,
            status=sub.status,
            denial_reason=sub.denial_reason,
            created_at=sub.created_at,
            api_name=api_name,
            user_name=user_name,
        )


# =============================================================================
# AUDIT LOG REPOSITORY
# =============================================================================


class AuditLogRepository(BaseRepository):
    """Repository for audit log operations."""

    async def log(
        self,
        user_id: str | None,
        tenant_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> int:
        """Create an audit log entry."""
        audit_log = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=details,
            ip_address=ip_address,
        )
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log.id

    async def search(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        action: str | None = None,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[AuditLogDTO]:
        """Search audit logs with filters."""
        # Convert time range to interval
        intervals = {
            "1h": "1 hour",
            "24h": "24 hours",
            "7d": "7 days",
            "30d": "30 days",
            "90d": "90 days",
        }
        interval = intervals.get(time_range, "24 hours")

        conditions = [
            AuditLog.timestamp > func.now() - text(f"INTERVAL '{interval}'")
        ]

        if tenant_id:
            conditions.append(AuditLog.tenant_id == tenant_id)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if action:
            conditions.append(AuditLog.action.ilike(f"%{action}%"))

        result = await self.session.execute(
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        return [self._to_dto(log) for log in result.scalars().all()]

    def _to_dto(self, log: AuditLog) -> AuditLogDTO:
        return AuditLogDTO(
            id=log.id,
            timestamp=log.timestamp,
            user_id=log.user_id,
            tenant_id=log.tenant_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            status=log.status,
            details=log.details,
            ip_address=str(log.ip_address) if log.ip_address else None,
        )


# =============================================================================
# UAC CONTRACT REPOSITORY
# =============================================================================


class UACContractRepository(BaseRepository):
    """Repository for UAC contract operations."""

    async def get_by_id(self, contract_id: str) -> UACContractDTO | None:
        """Get contract by ID."""
        result = await self.session.execute(
            select(UACContract).where(UACContract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        return self._to_dto(contract) if contract else None

    async def list(
        self,
        tenant_id: str | None = None,
        api_id: str | None = None,
        status: str | None = None,
    ) -> list[UACContractDTO]:
        """List contracts with filters."""
        conditions = []

        if tenant_id:
            conditions.append(UACContract.tenant_ids.contains([tenant_id]))
        if api_id:
            conditions.append(UACContract.api_ids.contains([api_id]))
        if status:
            conditions.append(UACContract.status == status)

        query = select(UACContract).order_by(UACContract.name)
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return [self._to_dto(contract) for contract in result.scalars().all()]

    def _to_dto(self, contract: UACContract) -> UACContractDTO:
        return UACContractDTO(
            id=contract.id,
            name=contract.name,
            description=contract.description,
            status=contract.status,
            terms=contract.terms or {},
            tenant_ids=list(contract.tenant_ids) if contract.tenant_ids else [],
            api_ids=list(contract.api_ids) if contract.api_ids else [],
        )
