"""
UAC Transformer — OpenAPI to UAC Contract conversion.

Fetches an OpenAPI spec from a URL, extracts paths/methods/operationIds/schemas,
and generates a UacContractSpec. Includes SSRF blocklist for URL fetching.
"""

import hashlib
import ipaddress
import logging
from urllib.parse import urlparse

import httpx

from src.schemas.uac import UacClassification, UacContractSpec, UacEndpointSpec

logger = logging.getLogger(__name__)

# SSRF blocklist — mirrors gateway's is_blocked_url() pattern
_BLOCKED_HOSTS = {"localhost", "0.0.0.0"}  # nosec B104 — SSRF blocklist, not a bind


def is_blocked_url(url: str) -> bool:
    """Check if a URL targets a private/internal IP range (SSRF protection).

    Mirrors stoa-gateway's proxy::dynamic::is_blocked_url() pattern.
    Blocks RFC 1918, loopback, link-local, and IPv6 ULA.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return True

    host = parsed.hostname
    if not host:
        return True

    if host in _BLOCKED_HOSTS:
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
    except ValueError:
        # Not an IP — hostname is allowed (DNS resolves at request time)
        pass

    return False


async def fetch_openapi_spec(url: str, timeout: float = 30.0) -> dict:
    """Fetch an OpenAPI spec from a URL with SSRF protection.

    Args:
        url: URL of the OpenAPI spec (JSON).
        timeout: HTTP timeout in seconds.

    Returns:
        Parsed OpenAPI spec as dict.

    Raises:
        ValueError: If URL is blocked (SSRF) or spec is invalid.
        httpx.HTTPError: If the fetch fails.
    """
    if is_blocked_url(url):
        raise ValueError(f"URL blocked by SSRF policy: {url}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def transform_openapi_to_uac(
    openapi_spec: dict,
    tenant_id: str,
    classification: UacClassification = UacClassification.H,
    backend_base_url: str | None = None,
    source_spec_url: str | None = None,
) -> UacContractSpec:
    """Transform a parsed OpenAPI spec into a UacContractSpec.

    Args:
        openapi_spec: Parsed OpenAPI 3.x spec.
        tenant_id: Owning tenant identifier.
        classification: ICT risk classification (default: H).
        backend_base_url: Override backend URL (default: from spec servers[0]).
        source_spec_url: URL where the spec was fetched from.

    Returns:
        UacContractSpec ready for deployment to the gateway.

    Raises:
        ValueError: If spec is missing required fields.
    """
    info = openapi_spec.get("info", {})
    title = info.get("title", "")
    if not title:
        raise ValueError("OpenAPI spec missing info.title")

    version = info.get("version", "1.0.0")
    description = info.get("description")

    # Derive contract name from title (kebab-case)
    name = _title_to_name(title)

    # Resolve backend base URL
    if not backend_base_url:
        servers = openapi_spec.get("servers", [])
        if servers:
            backend_base_url = servers[0].get("url", "")
        if not backend_base_url:
            backend_base_url = ""

    # Extract endpoints from paths
    endpoints = _extract_endpoints(openapi_spec, backend_base_url)

    # Compute spec hash
    spec_hash = _compute_spec_hash(openapi_spec)

    contract = UacContractSpec(
        name=name,
        version=version,
        tenant_id=tenant_id,
        display_name=title,
        description=description,
        classification=classification,
        endpoints=endpoints,
        source_spec_url=source_spec_url,
        spec_hash=spec_hash,
    )
    contract.refresh_policies()

    return contract


def _title_to_name(title: str) -> str:
    """Convert an OpenAPI title to a kebab-case contract name.

    E.g., "Payment Service API" -> "payment-service-api"
    """
    name = title.lower().strip()
    # Replace non-alphanumeric chars with hyphens
    result = []
    for ch in name:
        if ch.isalnum():
            result.append(ch)
        elif result and result[-1] != "-":
            result.append("-")

    cleaned = "".join(result).strip("-")
    # Ensure at least 2 chars for regex pattern
    if len(cleaned) < 2:
        cleaned = cleaned + "-api" if cleaned else "unnamed-api"
    return cleaned


def _extract_endpoints(openapi_spec: dict, backend_base_url: str) -> list[UacEndpointSpec]:
    """Extract UacEndpointSpec list from OpenAPI paths."""
    paths = openapi_spec.get("paths", {})
    endpoints: list[UacEndpointSpec] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        methods: list[str] = []
        operation_id: str | None = None
        input_schema: dict | None = None
        output_schema: dict | None = None

        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method not in path_item:
                continue
            methods.append(method.upper())
            operation = path_item[method]
            if isinstance(operation, dict):
                if not operation_id:
                    operation_id = operation.get("operationId")
                # Extract input schema from requestBody
                if not input_schema:
                    input_schema = _extract_request_schema(operation)
                # Extract output schema from 200/201 response
                if not output_schema:
                    output_schema = _extract_response_schema(operation)

        if not methods:
            continue

        backend_url = f"{backend_base_url.rstrip('/')}{path}" if backend_base_url else path

        endpoints.append(
            UacEndpointSpec(
                path=path,
                methods=methods,
                backend_url=backend_url,
                operation_id=operation_id,
                input_schema=input_schema,
                output_schema=output_schema,
            )
        )

    return endpoints


def _extract_request_schema(operation: dict) -> dict | None:
    """Extract request body JSON schema from an operation."""
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema")
    return schema if isinstance(schema, dict) else None


def _extract_response_schema(operation: dict) -> dict | None:
    """Extract response JSON schema from 200 or 201 response."""
    responses = operation.get("responses", {})
    for code in ("200", "201"):
        resp = responses.get(code, {})
        if not isinstance(resp, dict):
            continue
        content = resp.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


def _compute_spec_hash(openapi_spec: dict) -> str:
    """Compute SHA-256 hash of the spec for drift detection."""
    import json

    canonical = json.dumps(openapi_spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# =============================================================================
# UAC → OpenAPI reverse transform
# =============================================================================


def transform_uac_to_openapi(
    contract: UacContractSpec,
    openapi_version: str = "3.1.0",
) -> dict:
    """Transform a UacContractSpec back into an OpenAPI specification.

    Generates a valid OpenAPI 3.x document from a UAC contract, enabling
    round-trip fidelity: OpenAPI → UAC → OpenAPI.

    Args:
        contract: UAC contract to convert.
        openapi_version: Target OpenAPI version (default: 3.1.0).

    Returns:
        OpenAPI specification as a dict.
    """
    spec: dict = {
        "openapi": openapi_version,
        "info": _build_info(contract),
    }

    # Servers — derive from endpoint backend_urls
    servers = _build_servers(contract)
    if servers:
        spec["servers"] = servers

    # Paths — group endpoints by path
    paths = _build_paths(contract, servers)
    if paths:
        spec["paths"] = paths

    return spec


def _build_info(contract: UacContractSpec) -> dict:
    """Build OpenAPI info object from UAC contract."""
    info: dict = {
        "title": contract.display_name or contract.name,
        "version": contract.version,
    }
    if contract.description:
        info["description"] = contract.description
    return info


def _build_servers(contract: UacContractSpec) -> list[dict]:
    """Extract unique server base URLs from endpoint backend_urls."""
    base_urls: dict[str, bool] = {}
    for ep in contract.endpoints:
        if not ep.backend_url:
            continue
        # Extract base URL by removing the endpoint path suffix
        base = _extract_base_url(ep.backend_url, ep.path)
        if base and base not in base_urls:
            base_urls[base] = True
    return [{"url": url} for url in base_urls]


def _extract_base_url(backend_url: str, path: str) -> str:
    """Extract base URL from a backend URL by removing the path suffix.

    E.g., "https://api.example.com/v1/pets" with path "/pets"
    → "https://api.example.com/v1"
    """
    if not backend_url:
        return ""
    # If backend_url ends with the path, strip it
    if path and backend_url.endswith(path):
        return backend_url[: -len(path)].rstrip("/")
    # If it's just a path (no scheme), return empty
    if not backend_url.startswith(("http://", "https://")):
        return ""
    return backend_url


def _build_paths(contract: UacContractSpec, servers: list[dict]) -> dict:
    """Build OpenAPI paths object from UAC endpoints."""
    paths: dict = {}

    for ep in contract.endpoints:
        if ep.path not in paths:
            paths[ep.path] = {}

        path_item = paths[ep.path]
        for method in ep.methods:
            method_lower = method.lower()
            operation: dict = {}

            if ep.operation_id:
                operation["operationId"] = ep.operation_id

            # Request body for methods that typically have one
            if ep.input_schema and method_lower in ("post", "put", "patch"):
                operation["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": ep.input_schema,
                        }
                    }
                }

            # Response schema
            responses: dict = {}
            if method_lower == "delete":
                responses["204"] = {"description": "No Content"}
            elif ep.output_schema:
                success_code = "201" if method_lower == "post" else "200"
                responses[success_code] = {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": ep.output_schema,
                        }
                    },
                }
            else:
                responses["200"] = {"description": "Successful response"}

            operation["responses"] = responses
            path_item[method_lower] = operation

    return paths
