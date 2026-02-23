"""Mappers between Control Plane spec and AWS API Gateway native format.

Supports AWS API Gateway REST APIs (v1). HTTP APIs (v2) are not covered
because REST APIs provide usage plans, API keys, and stages — the full
feature set needed for STOA orchestration.

AWS REST API reference:
  https://docs.aws.amazon.com/apigateway/latest/api/
"""


def map_api_spec_to_aws(api_spec: dict, tenant_id: str) -> dict:
    """Map CP API spec to AWS REST API creation payload.

    Args:
        api_spec: Control Plane API specification dict.
        tenant_id: Tenant owning this API.

    Returns:
        Dict suitable for CreateRestApi / UpdateRestApi calls.
    """
    name = api_spec.get("name", "unnamed-api")
    safe_name = f"stoa-{tenant_id}-{name}".replace(" ", "-").lower()

    return {
        "name": safe_name,
        "description": api_spec.get("description", ""),
        "endpointConfiguration": {
            "types": [api_spec.get("endpoint_type", "REGIONAL")],
        },
        "tags": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-api-id": api_spec.get("id", ""),
            "stoa-api-name": name,
        },
    }


def map_aws_api_to_cp(api: dict) -> dict:
    """Map AWS REST API response to CP format.

    Args:
        api: AWS REST API dict from getRestApis response.

    Returns:
        Normalized CP API dict.
    """
    tags = api.get("tags", {})

    return {
        "id": tags.get("stoa-api-id", api.get("id", "")),
        "name": api.get("name", ""),
        "display_name": api.get("name", ""),
        "description": api.get("description", ""),
        "gateway_resource_id": api.get("id", ""),
        "gateway_type": "aws_apigateway",
        "created_at": api.get("createdDate"),
    }


def map_policy_to_aws_usage_plan(policy_spec: dict, tenant_id: str) -> dict:
    """Map CP policy spec to AWS usage plan creation payload.

    AWS usage plans encapsulate rate limiting (throttle) and quota.

    Args:
        policy_spec: CP policy spec (type=rate_limit).
        tenant_id: Tenant identifier.

    Returns:
        Dict suitable for CreateUsagePlan / UpdateUsagePlan calls.
    """
    policy_id = policy_spec.get("id", "")
    config = policy_spec.get("config", {})
    max_requests = config.get("max_requests", 100)
    window_seconds = config.get("window_seconds", 60)

    # AWS throttle is in requests/second
    rate_limit = max_requests / max(window_seconds, 1)
    burst_limit = config.get("burst_limit", max(int(rate_limit * 2), 1))

    plan: dict = {
        "name": f"stoa-{policy_id}",
        "description": policy_spec.get("description", policy_spec.get("name", "")),
        "throttle": {
            "rateLimit": rate_limit,
            "burstLimit": burst_limit,
        },
        "tags": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-policy-id": policy_id,
        },
    }

    # Optional quota (daily/weekly/monthly cap)
    quota_limit = config.get("quota_limit")
    quota_period = config.get("quota_period", "DAY")
    if quota_limit:
        plan["quota"] = {
            "limit": quota_limit,
            "period": quota_period,
        }

    return plan


def map_aws_usage_plan_to_policy(plan: dict) -> dict:
    """Map AWS usage plan back to CP policy format.

    Args:
        plan: AWS usage plan dict from getUsagePlans response.

    Returns:
        Normalized CP policy dict.
    """
    tags = plan.get("tags", {})
    throttle = plan.get("throttle", {})
    rate_limit = throttle.get("rateLimit", 0)
    burst_limit = throttle.get("burstLimit", 0)

    policy: dict = {
        "id": tags.get("stoa-policy-id", plan.get("id", "")),
        "name": plan.get("name", ""),
        "description": plan.get("description", ""),
        "type": "rate_limit",
        "gateway_type": "aws_apigateway",
        "config": {
            "max_requests": int(rate_limit * 60),
            "window_seconds": 60,
            "burst_limit": burst_limit,
        },
    }

    quota = plan.get("quota")
    if quota:
        policy["config"]["quota_limit"] = quota.get("limit")
        policy["config"]["quota_period"] = quota.get("period", "DAY")

    return policy


def map_app_spec_to_aws_api_key(app_spec: dict, tenant_id: str) -> dict:
    """Map CP application spec to AWS API key creation payload.

    Args:
        app_spec: CP application specification dict.
        tenant_id: Tenant identifier.

    Returns:
        Dict suitable for CreateApiKey call.
    """
    app_id = app_spec.get("id", "")
    name = app_spec.get("name", f"stoa-app-{app_id}")

    return {
        "name": f"stoa-{tenant_id}-{name}".replace(" ", "-").lower(),
        "description": app_spec.get("description", ""),
        "enabled": True,
        "tags": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-app-id": app_id,
            "stoa-subscription-id": app_spec.get("subscription_id", ""),
        },
    }


def map_aws_api_key_to_cp(key: dict) -> dict:
    """Map AWS API key back to CP application format.

    Args:
        key: AWS API key dict from getApiKeys response.

    Returns:
        Normalized CP application dict.
    """
    tags = key.get("tags", {})

    return {
        "id": tags.get("stoa-app-id", key.get("id", "")),
        "name": key.get("name", ""),
        "description": key.get("description", ""),
        "subscription_id": tags.get("stoa-subscription-id", ""),
        "gateway_resource_id": key.get("id", ""),
        "gateway_type": "aws_apigateway",
        "enabled": key.get("enabled", False),
        "created_at": key.get("createdDate"),
    }
