"""Mappers: translate Control Plane specs to Gravitee Management API v2 format."""


def map_api_spec_to_gravitee_v4(api_spec: dict, tenant_id: str) -> dict:
    """Map CP api_spec to a Gravitee v4 API definition.

    Ref: https://docs.gravitee.io/apim/3.x/apim_publisherguide_manage_apis.html
    """
    api_name = api_spec.get("api_name", api_spec.get("apiName", "unknown"))
    backend_url = api_spec.get("backend_url", api_spec.get("url", ""))
    methods = api_spec.get("methods", ["GET", "POST", "PUT", "DELETE"])

    return {
        "name": f"{tenant_id}-{api_name}",
        "apiVersion": "1.0.0",
        "definitionVersion": "V4",
        "type": "PROXY",
        "listeners": [
            {
                "type": "HTTP",
                "paths": [{"path": f"/apis/{tenant_id}/{api_name}"}],
                "entrypoints": [{"type": "http-proxy"}],
                "methods": methods,
            }
        ],
        "endpointGroups": [
            {
                "name": "default-group",
                "type": "http-proxy",
                "endpoints": [
                    {
                        "name": "default",
                        "type": "http-proxy",
                        "weight": 1,
                        "inheritConfiguration": False,
                        "configuration": {"target": backend_url},
                    }
                ],
            }
        ],
    }


def map_gravitee_api_to_cp(api: dict) -> dict:
    """Map a Gravitee API object to CP-normalized dict."""
    return {
        "id": api.get("id", ""),
        "name": api.get("name", ""),
        "state": api.get("state", ""),
        "visibility": api.get("visibility", ""),
        "definition_version": api.get("definitionVersion", ""),
        "deployed_at": api.get("deployedAt"),
    }


def map_policy_to_gravitee_plan(policy_spec: dict, api_name: str) -> dict:
    """Map STOA policy spec to a Gravitee Plan with rate-limit flow.

    Gravitee uses Plans to enforce policies like rate-limiting.
    Each plan has flows with policy steps.
    """
    policy_type = policy_spec.get("type", "")
    config = policy_spec.get("config", {})
    policy_id = policy_spec.get("id", "")

    if policy_type == "rate_limit":
        max_requests = config.get("maxRequests", 100)
        interval = config.get("intervalSeconds", 60)
        # Gravitee rate-limit uses "limit" and "periodTime" + "periodTimeUnit"
        if interval <= 1:
            period_time, period_unit = 1, "SECONDS"
        elif interval <= 60:
            period_time, period_unit = 1, "MINUTES"
        else:
            period_time, period_unit = interval // 60, "MINUTES"

        return {
            "name": f"stoa-rate-limit-{policy_id}",
            "description": f"STOA rate-limit policy {policy_id} for {api_name}",
            "validation": "AUTO",
            "security": {"type": "KEY_LESS"},
            "flows": [
                {
                    "name": "rate-limit-flow",
                    "enabled": True,
                    "request": [
                        {
                            "name": "Rate Limiting",
                            "policy": "rate-limit",
                            "configuration": {
                                "rate": {
                                    "limit": max_requests,
                                    "periodTime": period_time,
                                    "periodTimeUnit": period_unit,
                                }
                            },
                        }
                    ],
                }
            ],
            "tags": [f"stoa-policy-{policy_id}"],
        }

    # Generic policy fallback
    return {
        "name": f"stoa-{policy_type}-{policy_id}",
        "description": f"STOA {policy_type} policy {policy_id}",
        "validation": "AUTO",
        "security": {"type": "KEY_LESS"},
        "flows": [
            {
                "name": f"{policy_type}-flow",
                "enabled": True,
                "request": [
                    {
                        "name": policy_type,
                        "policy": policy_type.replace("_", "-"),
                        "configuration": config,
                    }
                ],
            }
        ],
        "tags": [f"stoa-policy-{policy_id}"],
    }


def map_gravitee_plan_to_policy(plan: dict) -> dict:
    """Map a Gravitee Plan to CP-normalized policy dict."""
    tags = plan.get("tags", [])
    stoa_id = ""
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("stoa-policy-"):
            stoa_id = tag.removeprefix("stoa-policy-")
            break

    # Extract rate-limit config from flows
    flows = plan.get("flows", [])
    policy_type = "unknown"
    cp_config: dict = {}

    for flow in flows:
        for step in flow.get("request", []):
            policy_name = step.get("policy", "")
            if policy_name == "rate-limit":
                policy_type = "rate_limit"
                rate_cfg = step.get("configuration", {}).get("rate", {})
                limit = rate_cfg.get("limit", 100)
                period_unit = rate_cfg.get("periodTimeUnit", "MINUTES")
                period_time = rate_cfg.get("periodTime", 1)
                interval = period_time if period_unit == "SECONDS" else period_time * 60
                cp_config = {"maxRequests": limit, "intervalSeconds": interval}
                break
            else:
                policy_type = policy_name.replace("-", "_")
                cp_config = step.get("configuration", {})
                break

    return {
        "id": stoa_id or plan.get("id", ""),
        "name": plan.get("name", ""),
        "type": policy_type,
        "config": cp_config,
        "plan_id": plan.get("id", ""),
    }


def map_app_spec_to_gravitee_app(app_spec: dict) -> dict:
    """Map CP app_spec to a Gravitee Application creation payload."""
    consumer_id = app_spec.get("consumer_external_id", app_spec.get("application_name", "unknown"))
    return {
        "name": consumer_id,
        "description": f"STOA consumer {consumer_id}",
        "settings": {
            "app": {
                "type": "SIMPLE",
            }
        },
    }


def map_gravitee_app_to_cp(app: dict) -> dict:
    """Map a Gravitee Application object to CP-normalized dict."""
    return {
        "id": app.get("id", ""),
        "name": app.get("name", ""),
        "status": app.get("status", ""),
        "created_at": app.get("created_at"),
    }
