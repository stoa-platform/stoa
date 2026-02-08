"""Integration tests for GatewayInstanceRepository with real PostgreSQL."""
import uuid

import pytest

from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from src.repositories.gateway_instance import GatewayInstanceRepository


@pytest.mark.integration
class TestGatewayInstanceRepositoryIntegration:
    async def test_create_gateway_instance(self, integration_db):
        repo = GatewayInstanceRepository(integration_db)
        instance = GatewayInstance(
            id=uuid.uuid4(),
            name="int-test-gw-create",
            display_name="Integration Test Gateway",
            gateway_type=GatewayType.STOA_EDGE_MCP,
            environment="dev",
            base_url="http://gateway.local:8080",
            auth_config={"type": "api_key"},
            status=GatewayInstanceStatus.ONLINE,
        )
        created = await repo.create(instance)

        assert created.id is not None
        assert created.name == "int-test-gw-create"
        assert created.gateway_type == GatewayType.STOA_EDGE_MCP

    async def test_get_by_name(self, integration_db):
        repo = GatewayInstanceRepository(integration_db)
        instance = GatewayInstance(
            id=uuid.uuid4(),
            name="int-test-gw-lookup",
            display_name="Lookup Gateway",
            gateway_type=GatewayType.KONG,
            environment="staging",
            base_url="http://kong.local:8001",
            auth_config={},
            status=GatewayInstanceStatus.OFFLINE,
        )
        await repo.create(instance)

        found = await repo.get_by_name("int-test-gw-lookup")
        assert found is not None
        assert found.display_name == "Lookup Gateway"

    async def test_update_health_status(self, integration_db):
        repo = GatewayInstanceRepository(integration_db)
        instance = GatewayInstance(
            id=uuid.uuid4(),
            name="int-test-gw-health",
            display_name="Health Gateway",
            gateway_type=GatewayType.STOA,
            environment="prod",
            base_url="http://stoa.local:8080",
            auth_config={},
            status=GatewayInstanceStatus.OFFLINE,
        )
        await repo.create(instance)

        updated = await repo.update_status(
            instance,
            GatewayInstanceStatus.ONLINE,
            health_details={"uptime": "99.9%"},
        )

        assert updated.status == GatewayInstanceStatus.ONLINE
        assert updated.health_details == {"uptime": "99.9%"}
        assert updated.last_health_check is not None

    async def test_list_with_filters(self, integration_db):
        repo = GatewayInstanceRepository(integration_db)

        for i, gw_type in enumerate([GatewayType.KONG, GatewayType.APIGEE, GatewayType.STOA]):
            instance = GatewayInstance(
                id=uuid.uuid4(),
                name=f"int-test-gw-filter-{i}",
                display_name=f"Filter Gateway {i}",
                gateway_type=gw_type,
                environment="dev",
                base_url=f"http://gw-{i}.local:8080",
                auth_config={},
                status=GatewayInstanceStatus.ONLINE,
            )
            await repo.create(instance)

        # Filter by type
        kong_gws, kong_total = await repo.list_all(gateway_type=GatewayType.KONG)
        assert kong_total >= 1
        assert all(gw.gateway_type == GatewayType.KONG for gw in kong_gws)
