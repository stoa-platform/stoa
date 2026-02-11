"""Mappers: translate Control Plane specs to Kong Admin API format (DB-less)."""


def map_api_spec_to_kong_service(api_spec: dict, tenant_id: str) -> dict:
    """Map CP api_spec to a Kong declarative service + route entry.

    Returns a dict suitable for inclusion in Kong's declarative YAML
    ``_format_version: "3.0"`` config.
    """
    api_name = api_spec.get("api_name", api_spec.get("apiName", "unknown"))
    backend_url = api_spec.get("backend_url", api_spec.get("url", ""))
    methods = api_spec.get("methods", ["GET", "POST", "PUT", "DELETE"])

    return {
        "name": f"{tenant_id}-{api_name}",
        "url": backend_url,
        "routes": [
            {
                "name": f"{tenant_id}-{api_name}-route",
                "paths": [f"/apis/{tenant_id}/{api_name}"],
                "methods": methods,
                "strip_path": True,
            }
        ],
    }


def map_kong_service_to_cp(service: dict) -> dict:
    """Map a Kong service object to CP-normalized API dict."""
    return {
        "id": service.get("id", ""),
        "name": service.get("name", ""),
        "host": service.get("host", ""),
        "port": service.get("port", 80),
        "protocol": service.get("protocol", "http"),
        "enabled": service.get("enabled", True),
    }
