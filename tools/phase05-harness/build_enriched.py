"""Deterministic enriched-single tool generator.

Reads an OpenAPI 3.x spec and emits a single MCP-style tool whose inputSchema
uses `action` as a discriminator (`const` per operation) and `params` as a
`oneOf` over per-operation param/body schemas.

Invariant: output is byte-stable for a given input spec. No LLM in the loop.

Frozen contract — do not refactor without bumping the SHA recorded in
README.md under "Generator pin".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def sanitize_op_id(method: str, path: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", path) or ["root"]
    return f"{method.lower()}_{'_'.join(parts)}"


def _merge_param_schema(op: dict[str, Any]) -> dict[str, Any]:
    """Assemble a JSON Schema `params` object from OpenAPI operation.

    Combines:
      - path/query/header parameters -> top-level properties
      - requestBody application/json schema -> merged properties (body wins on collision)
    """
    props: dict[str, Any] = {}
    required: list[str] = []

    for p in op.get("parameters", []) or []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not name:
            continue
        schema = p.get("schema") or {"type": "string"}
        prop = dict(schema)
        if p.get("description"):
            prop.setdefault("description", p["description"])
        prop["x-in"] = p.get("in", "query")
        props[name] = prop
        if p.get("required"):
            required.append(name)

    rb = (op.get("requestBody") or {}).get("content") or {}
    body_schema = (rb.get("application/json") or {}).get("schema") or {}
    if isinstance(body_schema, dict):
        if body_schema.get("type") == "object":
            for k, v in (body_schema.get("properties") or {}).items():
                props[k] = v
            for k in body_schema.get("required") or []:
                if k not in required:
                    required.append(k)
        elif body_schema.get("$ref") or body_schema.get("allOf") or body_schema.get("oneOf"):
            props.setdefault("body", body_schema)
            if (op.get("requestBody") or {}).get("required"):
                required.append("body")

    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = sorted(set(required))
    return schema


def _inject_discriminator(schema: dict[str, Any], op_id: str) -> dict[str, Any]:
    out = json.loads(json.dumps(schema, sort_keys=True))
    out.setdefault("properties", {})
    out["properties"]["action"] = {"type": "string", "const": op_id}
    req = set(out.get("required") or [])
    req.add("action")
    out["required"] = sorted(req)
    return out


def build_enriched(spec: dict[str, Any], tenant: str = "demo", api_id: str | None = None) -> dict[str, Any]:
    """Return a tool definition dict. Deterministic in input.

    Output shape:
        {
          "name": "{tenant}:{api}",
          "description": str,
          "inputSchema": {
            "type": "object",
            "required": ["action", "params"],
            "properties": {
              "action": {"type": "string", "enum": [...]},
              "params": {"oneOf": [{"$ref": "#/$defs/<op_id>"}, ...]},
            },
            "$defs": {<op_id>: {... "properties": {"action": {"const": "<op_id>"}, ...}}},
          }
        }
    """
    info = spec.get("info") or {}
    api_name = api_id or (info.get("title", "api").lower().replace(" ", "-"))
    ops: list[tuple[str, str, dict[str, Any]]] = []  # (op_id, method_path_key, op_obj)

    for path in sorted((spec.get("paths") or {}).keys()):
        path_item = spec["paths"][path] or {}
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            raw_id = op.get("operationId") or sanitize_op_id(method, path)
            op_id = re.sub(r"[^A-Za-z0-9_]", "_", raw_id)
            ops.append((op_id, f"{method.upper()} {path}", op))

    seen: set[str] = set()
    ordered_ops: list[tuple[str, str, dict[str, Any]]] = []
    for op_id, key, op in ops:
        unique_id = op_id
        i = 2
        while unique_id in seen:
            unique_id = f"{op_id}_{i}"
            i += 1
        seen.add(unique_id)
        ordered_ops.append((unique_id, key, op))

    defs: dict[str, Any] = {}
    action_enum: list[str] = []
    one_of: list[dict[str, Any]] = []
    for op_id, _key, op in ordered_ops:
        param_schema = _merge_param_schema(op)
        with_disc = _inject_discriminator(param_schema, op_id)
        desc = op.get("summary") or op.get("description") or ""
        if desc:
            with_disc.setdefault("description", desc)
        defs[op_id] = with_disc
        action_enum.append(op_id)
        one_of.append({"$ref": f"#/$defs/{op_id}"})

    tool = {
        "name": f"{tenant}:{api_name}",
        "description": info.get("description") or info.get("title") or api_name,
        "inputSchema": {
            "type": "object",
            "required": ["action", "params"],
            "properties": {
                "action": {"type": "string", "enum": sorted(action_enum)},
                "params": {"oneOf": one_of, "discriminator": {"propertyName": "action"}},
            },
            "$defs": defs,
        },
    }
    return tool


def build_per_op(spec: dict[str, Any], tenant: str = "demo", api_id: str | None = None) -> list[dict[str, Any]]:
    """Condition B: one tool per operation. Deterministic in input."""
    info = spec.get("info") or {}
    api_name = api_id or (info.get("title", "api").lower().replace(" ", "-"))
    tools: list[dict[str, Any]] = []
    for path in sorted((spec.get("paths") or {}).keys()):
        path_item = spec["paths"][path] or {}
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            raw_id = op.get("operationId") or sanitize_op_id(method, path)
            op_id = re.sub(r"[^A-Za-z0-9_]", "_", raw_id)
            params_schema = _merge_param_schema(op)
            tools.append(
                {
                    "name": f"{tenant}-{api_name}-{op_id}",
                    "description": op.get("summary") or op.get("description") or f"{method.upper()} {path}",
                    "inputSchema": params_schema,
                }
            )
    return sorted(tools, key=lambda t: t["name"])


def build_coarse(spec: dict[str, Any], tenant: str = "demo", api_id: str | None = None) -> dict[str, Any]:
    """Condition A: baseline coarse tool. One tool per API with opaque {action,params}."""
    info = spec.get("info") or {}
    api_name = api_id or (info.get("title", "api").lower().replace(" ", "-"))
    return {
        "name": f"{tenant}:{api_name}",
        "description": info.get("description") or info.get("title") or api_name,
        "inputSchema": {
            "type": "object",
            "required": ["action", "params"],
            "properties": {
                "action": {"type": "string", "description": "operation name"},
                "params": {"type": "object", "description": "operation parameters"},
            },
        },
    }


def spec_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generator_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--condition", choices=["coarse", "per-op", "enriched-single"], required=True)
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--api-id", default=None)
    ap.add_argument("--print-hash", action="store_true")
    args = ap.parse_args()

    spec = yaml.safe_load(args.spec.read_text())
    if args.condition == "coarse":
        out: Any = build_coarse(spec, args.tenant, args.api_id)
    elif args.condition == "per-op":
        out = build_per_op(spec, args.tenant, args.api_id)
    else:
        out = build_enriched(spec, args.tenant, args.api_id)

    if args.print_hash:
        print(f"spec_sha256={spec_sha256(args.spec)}")
        print(f"generator_sha256={generator_sha256()}")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
