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


def map_app_spec_to_route(app_spec: dict) -> dict:
    """Convert enriched app_spec to stoa-gateway sync_api format (CAB-1121 Phase 3).

    Used by provision_application to register the API route on the gateway
    before pushing the rate-limit policy.
    """
    api_id = app_spec.get("api_id", "")
    tenant_id = app_spec.get("tenant_id", "")
    app_name = app_spec.get("application_name", "unknown")
    return {
        "api_catalog_id": api_id,
        "api_name": app_name,
        "backend_url": app_spec.get("backend_url", ""),
        "methods": app_spec.get("methods", ["GET", "POST", "PUT", "DELETE"]),
        "spec_hash": "",
        "activated": True,
        "tenant_id": tenant_id,
    }


def map_quota_to_policy(app_spec: dict, subscription_id: str) -> dict | None:
    """Convert plan quota fields from enriched app_spec to rate-limit policy (CAB-1121 Phase 3).

    Returns None if no rate-limit quotas are defined.
    """
    rate_per_minute = app_spec.get("rate_limit_per_minute")
    rate_per_second = app_spec.get("rate_limit_per_second")

    if not rate_per_minute and not rate_per_second:
        return None

    consumer_ext_id = app_spec.get("consumer_external_id", "unknown")
    plan_slug = app_spec.get("plan_slug", "default")

    config = {
        "maxRequests": rate_per_minute or (rate_per_second * 60 if rate_per_second else 100),
        "intervalSeconds": 60,
    }

    # Include daily/monthly limits when present (CAB-1121 Phase 4)
    daily_limit = app_spec.get("daily_request_limit")
    monthly_limit = app_spec.get("monthly_request_limit")
    if daily_limit:
        config["dailyLimit"] = daily_limit
    if monthly_limit:
        config["monthlyLimit"] = monthly_limit

    return {
        "id": f"quota-{subscription_id}",
        "name": f"rate-limit-{consumer_ext_id}-{plan_slug}",
        "type": "rate_limit",
        "api_id": app_spec.get("api_id", ""),
        "config": config,
        "priority": 50,
    }
