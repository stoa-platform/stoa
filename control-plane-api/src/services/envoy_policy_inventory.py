"""Attribute the CP policy inventory without broadening an empty binding."""

from src.models.gateway_instance import GatewayInstance
from src.models.gateway_policy import GatewayPolicy, PolicyScope


def policy_inventory_item(policy: GatewayPolicy, gateway: GatewayInstance) -> dict:
    bindings = [
        b
        for b in policy.bindings
        if b.enabled and b.gateway_instance_id in (None, gateway.id) and b.tenant_id in (None, gateway.tenant_id)
    ]
    same_tenant = policy.tenant_id in (None, gateway.tenant_id)
    targets = sorted({str(b.api_catalog_id) for b in bindings if b.api_catalog_id}) if same_tenant else []
    applicable = False
    if same_tenant:
        if policy.scope == PolicyScope.API:
            applicable = bool(targets)
        elif policy.scope == PolicyScope.GATEWAY:
            applicable = any(b.gateway_instance_id == gateway.id and not b.api_catalog_id for b in bindings)
        elif policy.scope == PolicyScope.TENANT:
            applicable = bool(gateway.tenant_id) and any(
                b.tenant_id == gateway.tenant_id and not b.api_catalog_id for b in bindings
            )
    return {
        "id": str(policy.id),
        "name": policy.name,
        "policy_type": policy.policy_type.value,
        "config": policy.config,
        "priority": policy.priority,
        "enabled": policy.enabled,
        "scope": policy.scope.value,
        "api_catalog_ids": targets,
        "tenant_id": policy.tenant_id or (gateway.tenant_id if policy.scope == PolicyScope.TENANT else "") or "",
        "applicable": applicable,
    }
