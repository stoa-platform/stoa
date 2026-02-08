"""Integration tests for Contract model operations with real PostgreSQL."""
import uuid

import pytest
from sqlalchemy import select

from src.models.contract import Contract, ProtocolBinding, ProtocolType
from src.models.tenant import Tenant, TenantStatus
from src.repositories.tenant import TenantRepository


@pytest.mark.integration
class TestContractIntegration:
    async def _seed_tenant(self, db, tenant_id: str = "int-contract-tenant"):
        repo = TenantRepository(db)
        tenant = Tenant(
            id=tenant_id, name="Contract Test Tenant",
            status=TenantStatus.ACTIVE.value, settings={},
        )
        await repo.create(tenant)

    async def test_create_contract(self, integration_db):
        await self._seed_tenant(integration_db)

        contract = Contract(
            id=uuid.uuid4(),
            tenant_id="int-contract-tenant",
            name="payment-service",
            display_name="Payment Service API",
            version="1.0.0",
            status="draft",
        )
        integration_db.add(contract)
        await integration_db.flush()
        await integration_db.refresh(contract)

        assert contract.id is not None
        assert contract.name == "payment-service"
        assert contract.created_at is not None

    async def test_create_contract_with_bindings(self, integration_db):
        await self._seed_tenant(integration_db, "int-contract-bind")

        contract = Contract(
            id=uuid.uuid4(),
            tenant_id="int-contract-bind",
            name="order-service",
            version="2.0.0",
            status="published",
        )
        integration_db.add(contract)
        await integration_db.flush()

        rest_binding = ProtocolBinding(
            id=uuid.uuid4(),
            contract_id=contract.id,
            protocol=ProtocolType.REST,
            enabled=True,
            endpoint="/api/v1/orders",
        )
        mcp_binding = ProtocolBinding(
            id=uuid.uuid4(),
            contract_id=contract.id,
            protocol=ProtocolType.MCP,
            enabled=True,
            tool_name="create_order",
        )
        integration_db.add_all([rest_binding, mcp_binding])
        await integration_db.flush()

        # Query back
        result = await integration_db.execute(
            select(ProtocolBinding).where(ProtocolBinding.contract_id == contract.id)
        )
        bindings = result.scalars().all()
        assert len(bindings) == 2

        protocols = {b.protocol for b in bindings}
        assert ProtocolType.REST in protocols
        assert ProtocolType.MCP in protocols

    async def test_contract_status_transition(self, integration_db):
        await self._seed_tenant(integration_db, "int-contract-status")

        contract = Contract(
            id=uuid.uuid4(),
            tenant_id="int-contract-status",
            name="status-service",
            version="1.0.0",
            status="draft",
        )
        integration_db.add(contract)
        await integration_db.flush()

        # Publish
        contract.status = "published"
        await integration_db.flush()
        await integration_db.refresh(contract)
        assert contract.status == "published"

        # Deprecate
        contract.status = "deprecated"
        await integration_db.flush()
        await integration_db.refresh(contract)
        assert contract.status == "deprecated"

    async def test_list_contracts_by_tenant(self, integration_db):
        await self._seed_tenant(integration_db, "int-contract-list")

        for i in range(3):
            contract = Contract(
                id=uuid.uuid4(),
                tenant_id="int-contract-list",
                name=f"service-{i}",
                version="1.0.0",
                status="draft",
            )
            integration_db.add(contract)
        await integration_db.flush()

        result = await integration_db.execute(
            select(Contract).where(Contract.tenant_id == "int-contract-list")
        )
        contracts = result.scalars().all()
        assert len(contracts) == 3
