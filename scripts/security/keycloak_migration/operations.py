"""Field diffing and effective mapper reconciliation."""

import copy

from keycloak_migration.core import MAPPER_KEYS, identifier, require
from keycloak_migration.policy import mapper


def index(items, key):
    require(isinstance(items, list))
    result = {}
    for item in items:
        require(isinstance(item, dict) and key in item)
        identifier(item[key])
        require(item[key] not in result, "Ambiguous API inventory; nothing applied")
        result[item[key]] = item
    return result


def value_at(obj, key):
    for part in key:
        if not isinstance(obj, dict) or part not in obj:
            return {"exists": False}
        obj = obj[part]
    return {"exists": True, "value": copy.deepcopy(obj)}


def field_op(path, current, desired):
    changes = []
    for key, value in desired:
        before = value_at(current, key)
        after = {"exists": True, "value": value}
        if before != after:
            changes.append({"key": key, "before": before, "after": after})
    return {"kind": "fields", "path": path, "changes": changes} if changes else None


def mapper_view(obj):
    return {key: obj[key] for key in MAPPER_KEYS if key in obj}


def reconcile_mappers(api, path, definitions):
    existing = index(api.get(path), "name")
    future = copy.deepcopy(existing)
    ops = []
    for name, preset in sorted(definitions.items()):
        desired = mapper(preset, name)
        if name in existing:
            require(
                set(MAPPER_KEYS) <= set(existing[name]),
                "Incomplete managed mapper representation; nothing applied",
            )
        before = mapper_view(existing[name]) if name in existing else None
        if before != desired:
            ops.append(
                {"kind": "mapper", "path": path, "name": name, "before": before, "after": desired}
            )
        future[name] = desired
    return ops, list(future.values())


def validate_effective(mappers):
    tenants = [x for x in mappers if x.get("config", {}).get("claim.name") == "tenant_id"]
    require(len(tenants) <= 1, "Competing tenant claims; nothing applied")
    if tenants:
        obj = tenants[0]
        require(
            mapper_view(obj) == mapper("tenant", obj["name"]),
            "Unreviewed tenant mapper in effective scopes; nothing applied",
        )
    audiences = [
        x
        for x in mappers
        if x.get("config", {}).get("included.client.audience") == "control-plane-api"
    ]
    require(len(audiences) <= 1, "Competing API audience mappers; nothing applied")
    if audiences:
        obj = audiences[0]
        require(
            mapper_view(obj) == mapper("audience", obj["name"]),
            "Unreviewed API audience mapper; nothing applied",
        )
