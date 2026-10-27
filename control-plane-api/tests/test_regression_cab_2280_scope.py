"""Active policy inventory is attributed through real enabled bindings."""

from uuid import uuid4

import pytest

from src.config import settings
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyScope, PolicyType
from src.routers.gateway_internal import get_gateway_config
from tests.o1_support import local_session


@pytest.mark.asyncio
async def test_regression_cab_2280_policy_inventory_scope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "o1-local-test-key")
    async for db in local_session():
        gateway = GatewayInstance(
            id=uuid4(),
            name="link",
            display_name="Link",
            gateway_type=GatewayType.STOA,
            base_url="http://gateway.test",
            environment="test",
            tenant_id="tenant",
        )
        other = uuid4()
        catalog = uuid4()
        policies = []
        for name, scope, bindings in [
            ("bound", PolicyScope.API, [{"api_catalog_id": catalog, "gateway_instance_id": gateway.id}]),
            ("foreign", PolicyScope.API, [{"api_catalog_id": catalog, "gateway_instance_id": other}]),
            ("disabled-binding", PolicyScope.API, [{"api_catalog_id": catalog, "enabled": False}]),
            ("unbound", PolicyScope.API, []),
            ("gateway", PolicyScope.GATEWAY, [{"gateway_instance_id": gateway.id}]),
            ("tenant", PolicyScope.TENANT, [{"tenant_id": "tenant"}]),
            ("foreign-tenant", PolicyScope.TENANT, [{"tenant_id": "other"}]),
        ]:
            p = GatewayPolicy(
                id=uuid4(),
                name=name,
                policy_type=PolicyType.CORS,
                scope=scope,
                tenant_id="tenant",
                config={},
                enabled=True,
            )
            p.bindings = [GatewayPolicyBinding(id=uuid4(), **b) for b in bindings]
            policies.append(p)
        db.add_all([gateway, *policies])
        await db.commit()
        response = await get_gateway_config(gateway.id, x_gateway_key="o1-local-test-key", db=db)
        inventory = {p["name"]: p for p in response["pending_policies"]}
        assert inventory["bound"]["scope"] == "api"
        assert inventory["bound"]["api_catalog_ids"] == [str(catalog)]
        assert {p["name"] for p in inventory.values() if p["applicable"]} == {"bound", "gateway", "tenant"}
        assert all(not inventory[name]["api_catalog_ids"] for name in ("foreign", "disabled-binding", "unbound"))
