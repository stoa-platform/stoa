"""MCP tool expander (CAB-2113 Phase 0).

Turns a catalog API into a list of MCP tool descriptors ready to be consumed by
``stoa-gateway`` over ``GET /v1/internal/catalog/apis/expanded``. Two modes:

1. **Per-operation** (``openapi_spec`` provided): one tool per
   ``paths[].operations`` entry, with input schema merged from path params,
   query params and request body. Tool name follows the existing
   ``{tenant}:{api}:{operation}`` convention used by ``UacToolGenerator``.
2. **Coarse fallback** (``openapi_spec is None``): one tool with the legacy
   ``{action, params}`` schema — matches today's hardcoded gateway behaviour in
   ``stoa-gateway/src/mcp/tools/api_bridge.rs`` so ``/apis/expanded`` stays a
   drop-in replacement for ``/apis`` when a spec isn't available.

Pure function — no DB access, no I/O. Designed to be called from the
``/v1/internal/catalog/apis/expanded`` router once per request and is cheap
enough to not need caching at this stage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_HTTP_METHODS: tuple[str, ...] = ("get", "post", "put", "patch", "delete", "head", "options")


@dataclass(frozen=True)
class ExpandedTool:
    """MCP tool descriptor emitted by the expander.

    Immutable (``frozen=True``) so background refresh loops on the gateway
    side can't accidentally mutate registry state across ticks.
    """

    name: str
    description: str
    input_schema: dict[str, Any] | None
    backend_url: str
    http_method: str
    tenant_id: str
    path_pattern: str | None = None


def expand_api(
    api_id: str,
    tenant_id: str,
    api_name: str,
    backend_url: str,
    openapi_spec: dict[str, Any] | None,
) -> list[ExpandedTool]:
    """Expand a single catalog API into one or more MCP tool descriptors."""
    if openapi_spec is None:
        return [_coarse_tool(api_id, api_name, backend_url, tenant_id)]

    paths = openapi_spec.get("paths") or {}
    if not isinstance(paths, dict):
        return []

    tools: list[ExpandedTool] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            tools.append(
                _operation_to_tool(
                    api_id=api_id,
                    tenant_id=tenant_id,
                    backend_url=backend_url,
                    path=path,
                    method=method.upper(),
                    operation=operation,
                )
            )
    return tools


def _operation_to_tool(
    *,
    api_id: str,
    tenant_id: str,
    backend_url: str,
    path: str,
    method: str,
    operation: dict[str, Any],
) -> ExpandedTool:
    op_id = operation.get("operationId")
    name = _build_tool_name(tenant_id, api_id, op_id, path, method)
    description = _build_description(operation, path, method)
    input_schema = _build_input_schema(operation, path)

    return ExpandedTool(
        name=name,
        description=description,
        input_schema=input_schema,
        backend_url=backend_url,
        http_method=method,
        tenant_id=tenant_id,
        path_pattern=path,
    )


def _coarse_tool(api_id: str, api_name: str, backend_url: str, tenant_id: str) -> ExpandedTool:
    """Single coarse tool, matching today's ``api_bridge.rs`` behaviour verbatim."""
    description = api_name or api_id
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "API action to perform (e.g. get-status, list, create)",
            },
            "params": {
                "type": "object",
                "description": "Additional parameters for the API call",
            },
        },
        "required": [],
    }
    return ExpandedTool(
        name=api_id,
        description=description,
        input_schema=input_schema,
        backend_url=backend_url,
        http_method="POST",
        tenant_id=tenant_id,
    )


def _build_tool_name(
    tenant_id: str,
    api_id: str,
    operation_id: str | None,
    path: str,
    method: str,
) -> str:
    """Return ``{tenant}:{api}:{operation_slug}``.

    Slug rules mirror ``UacToolGenerator._build_tool_name`` so the naming stays
    consistent with tools coming from the UAC contract pipeline.
    """
    if operation_id:
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", operation_id).lower()
    else:
        path_slug = re.sub(r"[{}]", "", path)
        path_slug = re.sub(r"[^a-zA-Z0-9/]", "_", path_slug).strip("/_").replace("/", "_")
        slug = f"{method.lower()}_{path_slug}"
    return f"{tenant_id}:{api_id}:{slug}"


def _build_description(operation: dict[str, Any], path: str, method: str) -> str:
    summary = operation.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    desc = operation.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    return f"{method} {path}"


def _build_input_schema(operation: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Merge path + query parameters with requestBody into a single JSON Schema.

    Path-param substitution at call time happens gateway-side; we simply surface
    them as required string properties so the LLM knows to supply them.
    """
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for param in operation.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        location = param.get("in")
        if location not in ("path", "query"):
            continue
        name = param.get("name")
        if not isinstance(name, str):
            continue
        raw_schema = param.get("schema")
        schema: dict[str, Any] = raw_schema if isinstance(raw_schema, dict) else {"type": "string"}
        prop: dict[str, Any] = dict(schema)
        if description := param.get("description"):
            prop["description"] = description
        properties[name] = prop
        if param.get("required") or location == "path":
            required.append(name)

    body_schema = _extract_request_body_schema(operation)
    if body_schema and isinstance(body_schema.get("properties"), dict):
        for name, prop in body_schema["properties"].items():
            if name not in properties:
                properties[name] = prop
        for name in body_schema.get("required") or []:
            if name in properties and name not in required:
                required.append(name)
    elif body_schema:
        properties["body"] = body_schema

    # Fallback to path-only parameters if nothing was captured (matches
    # UacToolGenerator._build_input_schema behaviour).
    if not properties:
        path_params = re.findall(r"\{(\w+)\}", path)
        if not path_params:
            return None
        return {
            "type": "object",
            "properties": {p: {"type": "string", "description": f"Path parameter: {p}"} for p in path_params},
            "required": path_params,
        }

    return {"type": "object", "properties": properties, "required": required}


def _extract_request_body_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content")
    if not isinstance(content, dict):
        return None
    json_content = content.get("application/json")
    if not isinstance(json_content, dict):
        return None
    schema = json_content.get("schema")
    return schema if isinstance(schema, dict) else None
