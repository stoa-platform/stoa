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


def map_policy_to_kong_plugin(policy_spec: dict, service_name: str) -> dict:
    """Map STOA policy spec to a Kong plugin in declarative config format.

    Supported policy types:
    - rate_limit → rate-limiting plugin
    - cors → cors plugin
    """
    policy_type = policy_spec.get("type", "")
    config = policy_spec.get("config", {})

    if policy_type == "rate_limit":
        max_requests = config.get("maxRequests", 100)
        interval = config.get("intervalSeconds", 60)
        plugin_config = {"minute": max_requests} if interval == 60 else {"second": max_requests}
        return {
            "name": "rate-limiting",
            "service": service_name,
            "config": plugin_config,
            "tags": [f"stoa-policy-{policy_spec.get('id', '')}"],
        }

    if policy_type == "cors":
        return {
            "name": "cors",
            "service": service_name,
            "config": {
                "origins": config.get("origins", ["*"]),
                "methods": config.get("methods", ["GET", "POST", "PUT", "DELETE"]),
                "headers": config.get("headers", ["Content-Type", "Authorization"]),
                "max_age": config.get("max_age", 3600),
            },
            "tags": [f"stoa-policy-{policy_spec.get('id', '')}"],
        }

    return {
        "name": policy_type.replace("_", "-"),
        "service": service_name,
        "config": config,
        "tags": [f"stoa-policy-{policy_spec.get('id', '')}"],
    }


def map_kong_plugin_to_policy(plugin: dict) -> dict:
    """Map a Kong plugin object to CP-normalized policy dict."""
    plugin_name = plugin.get("name", "")
    kong_config = plugin.get("config", {})

    if plugin_name == "rate-limiting":
        minute = kong_config.get("minute", 0)
        second = kong_config.get("second", 0)
        max_requests = minute or (second * 60) or 100
        interval = 60 if minute else 1
        cp_config = {"maxRequests": max_requests, "intervalSeconds": interval}
        policy_type = "rate_limit"
    elif plugin_name == "cors":
        cp_config = {
            "origins": kong_config.get("origins", []),
            "methods": kong_config.get("methods", []),
            "headers": kong_config.get("headers", []),
            "max_age": kong_config.get("max_age", 3600),
        }
        policy_type = "cors"
    else:
        cp_config = kong_config
        policy_type = plugin_name.replace("-", "_")

    tags = plugin.get("tags") or []
    stoa_id = ""
    for tag in tags:
        if tag.startswith("stoa-policy-"):
            stoa_id = tag.removeprefix("stoa-policy-")
            break

    return {
        "id": stoa_id or plugin.get("id", ""),
        "name": plugin_name,
        "type": policy_type,
        "config": cp_config,
        "service": plugin.get("service", ""),
    }


def map_app_spec_to_kong_consumer(app_spec: dict) -> dict:
    """Map CP app_spec to a Kong consumer entry for declarative config.

    Returns a consumer dict with username, key-auth credentials, and
    optional rate-limiting plugin scoped to the consumer.
    """
    consumer_id = app_spec.get("consumer_external_id", app_spec.get("application_name", "unknown"))
    api_key = app_spec.get("api_key", f"key-{consumer_id}")

    consumer: dict = {
        "username": consumer_id,
        "keyauth_credentials": [{"key": api_key}],
        "tags": [f"stoa-consumer-{app_spec.get('subscription_id', '')}"],
    }

    rate_per_minute = app_spec.get("rate_limit_per_minute")
    rate_per_second = app_spec.get("rate_limit_per_second")
    if rate_per_minute or rate_per_second:
        rate = rate_per_minute or (rate_per_second * 60 if rate_per_second else 100)
        consumer["plugins"] = [
            {
                "name": "rate-limiting",
                "config": {"minute": rate},
            }
        ]

    return consumer


def map_kong_consumer_to_cp(consumer: dict) -> dict:
    """Map a Kong consumer object to CP-normalized application dict."""
    tags = consumer.get("tags") or []
    subscription_id = ""
    for tag in tags:
        if tag.startswith("stoa-consumer-"):
            subscription_id = tag.removeprefix("stoa-consumer-")
            break

    return {
        "id": consumer.get("id", ""),
        "name": consumer.get("username", ""),
        "username": consumer.get("username", ""),
        "subscription_id": subscription_id,
        "created_at": consumer.get("created_at"),
    }
