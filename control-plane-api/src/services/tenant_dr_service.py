"""
Tenant DR (Disaster Recovery) service — Export/Import (CAB-1474).

Export: collects all tenant configuration as a portable JSON archive.
Import: restores tenant configuration from an export archive with conflict resolution.
Sensitive data (API keys, secrets, encrypted auth configs) is excluded from export.
"""

import logging
import uuid
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
    ImportResult,
    TenantExportResponse,
    TenantImportRequest,
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


class TenantImportService:
    """Restores tenant configuration from an export archive.

    Supports 3 conflict resolution modes:
    - skip: ignore resources that already exist (default)
    - overwrite: replace existing resources with imported data
    - fail: abort on first conflict

    Dry-run mode validates the archive without applying changes.
    Subscriptions are skipped (API keys excluded from export for security).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_tenant(self, tenant_id: str, request: TenantImportRequest) -> ImportResult:
        """Import tenant configuration from an export archive."""
        mode = request.mode
        archive = request.archive
        dry_run = mode.dry_run
        conflict = mode.conflict_resolution

        # Verify target tenant exists
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise ValueError(f"Target tenant '{tenant_id}' not found")

        import_result = ImportResult(tenant_id=tenant_id, dry_run=dry_run)

        # Import each resource type in dependency order
        await self._import_backend_apis(tenant_id, archive.backend_apis, conflict, dry_run, import_result)
        await self._import_plans(tenant_id, archive.plans, conflict, dry_run, import_result)
        await self._import_consumers(tenant_id, archive.consumers, conflict, dry_run, import_result)
        await self._import_contracts(tenant_id, archive.contracts, conflict, dry_run, import_result)
        await self._import_policies(tenant_id, archive.policies, conflict, dry_run, import_result)
        await self._import_skills(tenant_id, archive.skills, conflict, dry_run, import_result)
        await self._import_webhooks(tenant_id, archive.webhooks, conflict, dry_run, import_result)
        await self._import_external_mcp_servers(
            tenant_id, archive.external_mcp_servers, conflict, dry_run, import_result
        )

        # Subscriptions skipped — API keys excluded from export
        if archive.subscriptions:
            import_result.skipped["subscriptions"] = len(archive.subscriptions)

        if not dry_run:
            await self.db.flush()

        import_result.success = len(import_result.errors) == 0

        total_created = sum(import_result.created.values())
        total_skipped = sum(import_result.skipped.values())
        logger.info(
            f"Import {'(dry-run) ' if dry_run else ''}tenant {tenant_id}: "
            f"{total_created} created, {total_skipped} skipped, {len(import_result.errors)} errors"
        )

        return import_result

    async def _import_backend_apis(
        self,
        tenant_id: str,
        apis: list[ExportedBackendApi],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for api in apis:
            existing = await self.db.execute(
                select(BackendApi).where(BackendApi.tenant_id == tenant_id, BackendApi.name == api.name)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"backend_api '{api.name}' already exists")
                    return
                skipped += 1
                if conflict == "overwrite" and not dry_run:
                    await self._overwrite_backend_api(tenant_id, api)
                continue
            if not dry_run:
                self.db.add(
                    BackendApi(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        name=api.name,
                        display_name=api.display_name,
                        description=api.description,
                        backend_url=api.backend_url or "",
                        openapi_spec_url=api.openapi_spec_url,
                        auth_type=api.auth_type or "none",
                        status=api.status or "draft",
                    )
                )
            created += 1
        if created:
            result.created["backend_apis"] = created
        if skipped:
            result.skipped["backend_apis"] = skipped

    async def _overwrite_backend_api(self, tenant_id: str, api: ExportedBackendApi) -> None:
        existing = await self.db.execute(
            select(BackendApi).where(BackendApi.tenant_id == tenant_id, BackendApi.name == api.name)
        )
        obj = existing.scalar_one()
        obj.display_name = api.display_name
        obj.description = api.description
        obj.backend_url = api.backend_url or obj.backend_url
        obj.openapi_spec_url = api.openapi_spec_url
        obj.auth_type = api.auth_type or obj.auth_type
        obj.status = api.status or obj.status

    async def _import_plans(
        self,
        tenant_id: str,
        plans: list[ExportedPlan],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for plan in plans:
            existing = await self.db.execute(select(Plan).where(Plan.tenant_id == tenant_id, Plan.slug == plan.slug))
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"plan '{plan.slug}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                self.db.add(
                    Plan(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        slug=plan.slug,
                        name=plan.name,
                        description=plan.description,
                        rate_limit_per_second=plan.rate_limit_per_second,
                        rate_limit_per_minute=plan.rate_limit_per_minute,
                        daily_request_limit=plan.daily_request_limit,
                        monthly_request_limit=plan.monthly_request_limit,
                        burst_limit=plan.burst_limit,
                        requires_approval=plan.requires_approval,
                        status=plan.status or "active",
                    )
                )
            created += 1
        if created:
            result.created["plans"] = created
        if skipped:
            result.skipped["plans"] = skipped

    async def _import_consumers(
        self,
        tenant_id: str,
        consumers: list[ExportedConsumer],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for consumer in consumers:
            existing = await self.db.execute(
                select(Consumer).where(Consumer.tenant_id == tenant_id, Consumer.external_id == consumer.external_id)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"consumer '{consumer.external_id}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                self.db.add(
                    Consumer(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        external_id=consumer.external_id,
                        name=consumer.name,
                        email=consumer.email,
                        company=consumer.company,
                        description=consumer.description,
                        status=consumer.status or "active",
                        consumer_metadata=consumer.consumer_metadata,
                    )
                )
            created += 1
        if created:
            result.created["consumers"] = created
        if skipped:
            result.skipped["consumers"] = skipped

    async def _import_contracts(
        self,
        tenant_id: str,
        contracts: list[ExportedContract],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for contract in contracts:
            existing = await self.db.execute(
                select(Contract).where(Contract.tenant_id == tenant_id, Contract.name == contract.name)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"contract '{contract.name}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                contract_id = uuid.uuid4()
                self.db.add(
                    Contract(
                        id=contract_id,
                        tenant_id=tenant_id,
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
                    )
                )
                # Import bindings
                for binding in contract.bindings:
                    self.db.add(
                        ProtocolBinding(
                            id=uuid.uuid4(),
                            contract_id=contract_id,
                            protocol=binding.get("protocol", "rest"),
                            enabled=binding.get("enabled", True),
                            endpoint=binding.get("endpoint"),
                            tool_name=binding.get("tool_name"),
                        )
                    )
            created += 1
        if created:
            result.created["contracts"] = created
        if skipped:
            result.skipped["contracts"] = skipped

    async def _import_policies(
        self,
        tenant_id: str,
        policies: list[ExportedPolicy],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for policy in policies:
            existing = await self.db.execute(
                select(GatewayPolicy).where(GatewayPolicy.tenant_id == tenant_id, GatewayPolicy.name == policy.name)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"policy '{policy.name}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                self.db.add(
                    GatewayPolicy(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        name=policy.name,
                        description=policy.description,
                        policy_type=policy.policy_type,
                        scope="tenant",
                        config=policy.config or {},
                        enabled=policy.enabled,
                    )
                )
            created += 1
        if created:
            result.created["policies"] = created
        if skipped:
            result.skipped["policies"] = skipped

    async def _import_skills(
        self,
        tenant_id: str,
        skills: list[ExportedSkill],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for skill in skills:
            existing = await self.db.execute(
                select(Skill).where(Skill.tenant_id == tenant_id, Skill.name == skill.name, Skill.scope == skill.scope)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"skill '{skill.name}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                self.db.add(
                    Skill(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        name=skill.name,
                        description=skill.description,
                        scope=skill.scope,
                        priority=skill.priority,
                        instructions=skill.instructions,
                        tool_ref=skill.tool_ref,
                        user_ref=skill.user_ref,
                        enabled=skill.enabled,
                    )
                )
            created += 1
        if created:
            result.created["skills"] = created
        if skipped:
            result.skipped["skills"] = skipped

    async def _import_webhooks(
        self,
        tenant_id: str,
        webhooks: list[ExportedWebhook],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for webhook in webhooks:
            existing = await self.db.execute(
                select(TenantWebhook).where(TenantWebhook.tenant_id == tenant_id, TenantWebhook.name == webhook.name)
            )
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"webhook '{webhook.name}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                self.db.add(
                    TenantWebhook(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        name=webhook.name,
                        url=webhook.url,
                        events=webhook.events,
                        enabled=webhook.enabled,
                    )
                )
            created += 1
        if created:
            result.created["webhooks"] = created
        if skipped:
            result.skipped["webhooks"] = skipped

    async def _import_external_mcp_servers(
        self,
        tenant_id: str,
        servers: list[ExportedExternalMcpServer],
        conflict: str,
        dry_run: bool,
        result: ImportResult,
    ) -> None:
        created = 0
        skipped = 0
        for server in servers:
            existing = await self.db.execute(select(ExternalMCPServer).where(ExternalMCPServer.name == server.name))
            if existing.scalar_one_or_none():
                if conflict == "fail":
                    result.errors.append(f"mcp_server '{server.name}' already exists")
                    return
                skipped += 1
                continue
            if not dry_run:
                server_id = uuid.uuid4()
                self.db.add(
                    ExternalMCPServer(
                        id=server_id,
                        tenant_id=tenant_id,
                        name=server.name,
                        display_name=server.name,
                        base_url=server.base_url,
                        description=server.description,
                        transport="sse",
                        auth_type="none",
                        enabled=server.enabled,
                    )
                )
                # Import tools
                for tool in server.tools:
                    self.db.add(
                        ExternalMCPServerTool(
                            id=uuid.uuid4(),
                            server_id=server_id,
                            name=tool.get("name", "unknown"),
                            namespaced_name=f"{server.name}/{tool.get('name', 'unknown')}",
                            description=tool.get("description"),
                            input_schema=tool.get("input_schema"),
                            enabled=True,
                        )
                    )
            created += 1
        if created:
            result.created["external_mcp_servers"] = created
        if skipped:
            result.skipped["external_mcp_servers"] = skipped
