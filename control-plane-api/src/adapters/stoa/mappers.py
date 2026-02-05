"""Mappers: translate Control Plane specs to stoa-gateway admin API format."""


def map_api_spec_to_stoa(api_spec: dict, tenant_id: str) -> dict:
    """Map CP desired_state / api_spec to stoa-gateway admin API payload.

    The stoa-gateway admin API expects:
    {id, name, tenant_id, path_prefix, backend_url, methods, spec_hash, activated}
    """
    api_name = api_spec.get("api_name", api_spec.get("apiName", "unknown"))
    return {
        "id": api_spec.get("api_catalog_id", ""),
        "name": api_name,
        "tenant_id": tenant_id,
        "path_prefix": f"/apis/{tenant_id}/{api_name}",
        "backend_url": api_spec.get("backend_url", api_spec.get("url", "")),
        "methods": api_spec.get("methods", ["GET", "POST", "PUT", "DELETE"]),
        "spec_hash": api_spec.get("spec_hash", ""),
        "activated": api_spec.get("activated", True),
    }


def map_policy_to_stoa(policy_spec: dict) -> dict:
    """Map CP policy spec to stoa-gateway admin API payload.

    The stoa-gateway admin API expects:
    {id, name, policy_type, config, priority, api_id}
    """
    return {
        "id": policy_spec.get("id", ""),
        "name": policy_spec.get("name", ""),
        "policy_type": policy_spec.get("type", ""),
        "config": policy_spec.get("config", {}),
        "priority": policy_spec.get("priority", 100),
        "api_id": policy_spec.get("api_id", ""),
    }
