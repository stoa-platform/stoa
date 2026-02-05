"""Repository for gateway policy and policy binding CRUD operations."""
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyType


class GatewayPolicyRepository:
    """Repository for gateway policy database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, policy: GatewayPolicy) -> GatewayPolicy:
        """Create a new gateway policy."""
        self.session.add(policy)
        await self.session.flush()
        await self.session.refresh(policy)
        return policy

    async def get_by_id(self, policy_id: UUID) -> GatewayPolicy | None:
        """Get policy by ID with bindings eagerly loaded."""
        result = await self.session.execute(
            select(GatewayPolicy)
            .options(selectinload(GatewayPolicy.bindings))
            .where(GatewayPolicy.id == policy_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        tenant_id: str | None = None,
        policy_type: PolicyType | None = None,
    ) -> list[GatewayPolicy]:
        """List policies with optional filters, ordered by priority."""
        query = select(GatewayPolicy).options(selectinload(GatewayPolicy.bindings))

        if tenant_id is not None:
            # Include tenant-specific and platform-wide (null tenant) policies
            query = query.where(
                or_(
                    GatewayPolicy.tenant_id == tenant_id,
                    GatewayPolicy.tenant_id.is_(None),
                )
            )
        if policy_type is not None:
            query = query.where(GatewayPolicy.policy_type == policy_type)

        query = query.order_by(GatewayPolicy.priority, GatewayPolicy.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, policy: GatewayPolicy) -> GatewayPolicy:
        """Update a policy (caller modifies fields before calling)."""
        await self.session.flush()
        await self.session.refresh(policy)
        return policy

    async def delete(self, policy: GatewayPolicy) -> None:
        """Delete a policy (cascades to bindings)."""
        await self.session.delete(policy)
        await self.session.flush()

    async def get_policies_for_deployment(
        self,
        api_catalog_id: UUID,
        gateway_instance_id: UUID,
        tenant_id: str,
    ) -> list[GatewayPolicy]:
        """Resolve all policies that apply to a deployment.

        Matches policies via bindings with:
        1. API-specific bindings (api_catalog_id + gateway_instance_id)
        2. Gateway-wide bindings (gateway_instance_id only)
        3. Tenant-wide bindings (tenant_id only)

        Returns enabled policies ordered by priority.
        """
        result = await self.session.execute(
            select(GatewayPolicy)
            .join(GatewayPolicyBinding, GatewayPolicy.id == GatewayPolicyBinding.policy_id)
            .where(
                GatewayPolicy.enabled.is_(True),
                GatewayPolicyBinding.enabled.is_(True),
                or_(
                    # API-level: exact match on api + gateway
                    (
                        GatewayPolicyBinding.api_catalog_id == api_catalog_id
                    ) & (
                        GatewayPolicyBinding.gateway_instance_id == gateway_instance_id
                    ),
                    # Gateway-level: gateway match, no api
                    (
                        GatewayPolicyBinding.gateway_instance_id == gateway_instance_id
                    ) & (
                        GatewayPolicyBinding.api_catalog_id.is_(None)
                    ),
                    # Tenant-level: tenant match, no api or gateway
                    (
                        GatewayPolicyBinding.tenant_id == tenant_id
                    ) & (
                        GatewayPolicyBinding.api_catalog_id.is_(None)
                    ) & (
                        GatewayPolicyBinding.gateway_instance_id.is_(None)
                    ),
                ),
            )
            .order_by(GatewayPolicy.priority, GatewayPolicy.name)
        )
        return list(result.scalars().all())


class GatewayPolicyBindingRepository:
    """Repository for gateway policy binding operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, binding: GatewayPolicyBinding) -> GatewayPolicyBinding:
        """Create a new policy binding."""
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def get_by_id(self, binding_id: UUID) -> GatewayPolicyBinding | None:
        """Get binding by ID."""
        result = await self.session.execute(
            select(GatewayPolicyBinding).where(GatewayPolicyBinding.id == binding_id)
        )
        return result.scalar_one_or_none()

    async def list_by_policy(self, policy_id: UUID) -> list[GatewayPolicyBinding]:
        """List all bindings for a policy."""
        result = await self.session.execute(
            select(GatewayPolicyBinding)
            .where(GatewayPolicyBinding.policy_id == policy_id)
            .order_by(GatewayPolicyBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, binding: GatewayPolicyBinding) -> None:
        """Delete a binding."""
        await self.session.delete(binding)
        await self.session.flush()
