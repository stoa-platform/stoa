"""
Tenant DR (Disaster Recovery) service — Export/Import (CAB-1474).

Exports all tenant configuration as a portable JSON archive.
Sensitive data (API keys, secrets, encrypted auth configs) is excluded.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.backend_api import BackendApi
from ..models.consumer import Consumer
from ..models.contract import Contract, ProtocolBinding
from ..models.external_mcp_server import ExternalMCPServer, ExternalMCPServerTool
from ..models.gateway_policy import GatewayPolicy
from ..models.plan import Plan
from ..models.skill import Skill
from ..models.subscription import Subscription
from ..models.tenant import Tenant
from ..models.webhook import TenantWebhook
from ..schemas.tenant_dr import (
    ExportedBackendApi,
    ExportedConsumer,
    ExportedContract,
    ExportedExternalMcpServer,
    ExportedPlan,
    ExportedPolicy,
    ExportedSkill,
    ExportedSubscription,
    ExportedWebhook,
    ExportMetadata,
    TenantExportResponse,
)

logger = logging.getLogger(__name__)


class TenantExportService:
    """Collects all tenant configuration data for export."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_tenant(self, tenant_id: str) -> TenantExportResponse:
        """Export all configuration for a tenant as a portable archive.

        Excludes sensitive data: API key hashes, encrypted auth configs,
        webhook secrets, and runtime state (deployments, logs, traces).
        """
        # Verify tenant exists
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        # Collect all resources in parallel-style sequential queries
        backend_apis = await self._export_backend_apis(tenant_id)
        contracts = await self._export_contracts(tenant_id)
        consumers = await self._export_consumers(tenant_id)
        plans = await self._export_plans(tenant_id)
        subscriptions = await self._export_subscriptions(tenant_id)
        policies = await self._export_policies(tenant_id)
        skills = await self._export_skills(tenant_id)
        webhooks = await self._export_webhooks(tenant_id)
        mcp_servers = await self._export_external_mcp_servers(tenant_id)

        resource_counts = {
            "backend_apis": len(backend_apis),
            "contracts": len(contracts),
            "consumers": len(consumers),
            "plans": len(plans),
            "subscriptions": len(subscriptions),
            "policies": len(policies),
            "skills": len(skills),
            "webhooks": len(webhooks),
            "external_mcp_servers": len(mcp_servers),
        }

        metadata = ExportMetadata(
            exported_at=datetime.now(UTC),
            tenant_id=tenant_id,
            tenant_name=tenant.name,
            resource_counts=resource_counts,
        )

        logger.info(
            f"Exported tenant {tenant_id}: {sum(resource_counts.values())} resources across "
            f"{sum(1 for v in resource_counts.values() if v > 0)} categories"
        )

        return TenantExportResponse(
            metadata=metadata,
            backend_apis=backend_apis,
            contracts=contracts,
            consumers=consumers,
            plans=plans,
            subscriptions=subscriptions,
            policies=policies,
            skills=skills,
            webhooks=webhooks,
            external_mcp_servers=mcp_servers,
        )

    async def _export_backend_apis(self, tenant_id: str) -> list[ExportedBackendApi]:
        result = await self.db.execute(select(BackendApi).where(BackendApi.tenant_id == tenant_id))
        apis = result.scalars().all()
        return [
            ExportedBackendApi(
                id=api.id,
                name=api.name,
                display_name=api.display_name,
                description=api.description,
                backend_url=api.backend_url,
                openapi_spec_url=api.openapi_spec_url,
                auth_type=str(api.auth_type) if api.auth_type else None,
                status=str(api.status) if api.status else None,
                created_at=api.created_at,
            )
            for api in apis
        ]

    async def _export_contracts(self, tenant_id: str) -> list[ExportedContract]:
        result = await self.db.execute(select(Contract).where(Contract.tenant_id == tenant_id))
        contracts = result.scalars().all()

        exported = []
        for contract in contracts:
            # Fetch bindings for this contract
            bindings_result = await self.db.execute(
                select(ProtocolBinding).where(ProtocolBinding.contract_id == contract.id)
            )
            bindings = bindings_result.scalars().all()
            binding_dicts = [
                {
                    "protocol": str(b.protocol),
                    "enabled": b.enabled,
                    "endpoint": b.endpoint,
                    "tool_name": b.tool_name,
                }
                for b in bindings
            ]

            exported.append(
                ExportedContract(
                    id=contract.id,
                    name=contract.name,
                    display_name=contract.display_name,
                    description=contract.description,
                    version=contract.version,
                    status=contract.status,
                    openapi_spec_url=contract.openapi_spec_url,
                    deprecated_at=contract.deprecated_at,
                    sunset_at=contract.sunset_at,
                    deprecation_reason=contract.deprecation_reason,
                    grace_period_days=contract.grace_period_days,
                    bindings=binding_dicts,
                    created_at=contract.created_at,
                )
            )
        return exported

    async def _export_consumers(self, tenant_id: str) -> list[ExportedConsumer]:
        result = await self.db.execute(select(Consumer).where(Consumer.tenant_id == tenant_id))
        consumers = result.scalars().all()
        return [
            ExportedConsumer(
                id=c.id,
                external_id=c.external_id,
                name=c.name,
                email=c.email,
                company=c.company,
                description=c.description,
                status=str(c.status),
                consumer_metadata=c.consumer_metadata,
                created_at=c.created_at,
            )
            for c in consumers
        ]

    async def _export_plans(self, tenant_id: str) -> list[ExportedPlan]:
        result = await self.db.execute(select(Plan).where(Plan.tenant_id == tenant_id))
        plans = result.scalars().all()
        return [
            ExportedPlan(
                id=p.id,
                slug=p.slug,
                name=p.name,
                description=p.description,
                rate_limit_per_second=p.rate_limit_per_second,
                rate_limit_per_minute=p.rate_limit_per_minute,
                daily_request_limit=p.daily_request_limit,
                monthly_request_limit=p.monthly_request_limit,
                burst_limit=p.burst_limit,
                requires_approval=p.requires_approval or False,
                status=str(p.status) if p.status else None,
                created_at=p.created_at,
            )
            for p in plans
        ]

    async def _export_subscriptions(self, tenant_id: str) -> list[ExportedSubscription]:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        subs = result.scalars().all()
        return [
            ExportedSubscription(
                id=s.id,
                application_id=s.application_id,
                application_name=s.application_name,
                subscriber_email=s.subscriber_email,
                api_id=s.api_id,
                api_name=s.api_name,
                plan_id=str(s.plan_id) if s.plan_id else None,
                status=str(s.status),
                created_at=s.created_at,
            )
            for s in subs
        ]

    async def _export_policies(self, tenant_id: str) -> list[ExportedPolicy]:
        result = await self.db.execute(select(GatewayPolicy).where(GatewayPolicy.tenant_id == tenant_id))
        policies = result.scalars().all()
        return [
            ExportedPolicy(
                id=p.id,
                name=p.name,
                description=p.description,
                policy_type=str(p.policy_type),
                config=p.config,
                enabled=p.enabled if p.enabled is not None else True,
                created_at=p.created_at,
            )
            for p in policies
        ]

    async def _export_skills(self, tenant_id: str) -> list[ExportedSkill]:
        result = await self.db.execute(select(Skill).where(Skill.tenant_id == tenant_id))
        skills = result.scalars().all()
        return [
            ExportedSkill(
                id=s.id,
                name=s.name,
                description=s.description,
                scope=str(s.scope),
                priority=s.priority,
                instructions=s.instructions,
                tool_ref=s.tool_ref,
                user_ref=s.user_ref,
                enabled=s.enabled,
            )
            for s in skills
        ]

    async def _export_webhooks(self, tenant_id: str) -> list[ExportedWebhook]:
        result = await self.db.execute(select(TenantWebhook).where(TenantWebhook.tenant_id == tenant_id))
        webhooks = result.scalars().all()
        return [
            ExportedWebhook(
                id=w.id,
                name=w.name,
                url=w.url,
                events=w.events or [],
                enabled=w.enabled if w.enabled is not None else True,
                created_at=w.created_at,
            )
            for w in webhooks
        ]

    async def _export_external_mcp_servers(self, tenant_id: str) -> list[ExportedExternalMcpServer]:
        result = await self.db.execute(select(ExternalMCPServer).where(ExternalMCPServer.tenant_id == tenant_id))
        servers = result.scalars().all()

        exported = []
        for server in servers:
            # Fetch tools for this server
            tools_result = await self.db.execute(
                select(ExternalMCPServerTool).where(ExternalMCPServerTool.server_id == server.id)
            )
            tools = tools_result.scalars().all()
            tool_dicts = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]

            exported.append(
                ExportedExternalMcpServer(
                    id=server.id,
                    name=server.name,
                    base_url=server.base_url,
                    description=server.description,
                    enabled=server.enabled if server.enabled is not None else True,
                    tools=tool_dicts,
                    created_at=server.created_at,
                )
            )
        return exported
