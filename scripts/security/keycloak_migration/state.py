"""State reads, redacted previews and scoped writes."""

import copy
import json

from keycloak_migration.core import identifier, require
from keycloak_migration.operations import index, mapper_view, value_at


def read_state(api, op):
    if op["kind"] == "fields":
        obj = api.get(op["path"])
        return [value_at(obj, c["key"]) for c in op["changes"]], obj
    items = index(api.get(op["path"]), "name")
    obj = items.get(op["name"])
    return mapper_view(obj) if obj is not None else None, obj


def expected(op, side):
    return [c[side] for c in op["changes"]] if op["kind"] == "fields" else op[side]


def preview(ops, output, reverse=False):
    """Never print URL paths, IDs, string values, server messages or response bodies."""

    def safe(value):
        if isinstance(value, dict) and "exists" in value:
            return safe(value.get("value")) if value["exists"] else "absent"
        if value is None or type(value) in (bool, int):
            return value
        if isinstance(value, list):
            return {"redacted_items": len(value)}
        return "[MASKED]"

    for number, op in enumerate(ops, 1):
        before, after = ("after", "before") if reverse else ("before", "after")
        changes = op["changes"] if op["kind"] == "fields" else [op]
        for change in changes:
            # Field names are constants produced by the planner, not remote strings.
            field = ".".join(change["key"]) if "key" in change else "protocol-mapper"
            print(
                json.dumps(
                    {
                        "operation": number,
                        "field": field,
                        "before": safe(change[before]),
                        "after": safe(change[after]),
                    }
                ),
                file=output,
            )
    print(
        json.dumps({"operations": len(ops), "mode": "rollback" if reverse else "migration"}),
        file=output,
    )
    output.flush()


def write_state(api, op, side, current):
    if op["kind"] == "mapper":
        desired = op[side]
        if desired is None:
            require(current is not None)
            api.request("DELETE", op["path"] + "/" + identifier(current["id"]))
        elif current is None:
            api.request("POST", op["path"], desired)
        else:
            payload = dict(current, **desired)
            api.request("PUT", op["path"] + "/" + identifier(current["id"]), payload)
        return
    payload = {}
    for change in op["changes"]:
        key, value = change["key"], change[side]
        if len(key) == 1:
            require(value["exists"], "Missing original scalar field: manual rollback required")
            payload[key[0]] = value["value"]
        else:
            require(key[0] == "attributes" and len(key) == 2)
            if "attributes" not in payload:
                payload["attributes"] = copy.deepcopy(current.get("attributes", {}))
            if value["exists"]:
                payload["attributes"][key[1]] = value["value"]
            else:
                payload["attributes"].pop(key[1], None)
    if op["path"].startswith("/identity-provider/"):
        # Keycloak's IdP update consumes a full provider representation. Preserve
        # config, including server-side secret placeholders; never journal it.
        payload = dict(current, **payload)
    api.request("PUT", op["path"], payload)
