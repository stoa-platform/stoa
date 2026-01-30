"""Mappers: STOA YAML specs → webMethods REST API payloads.

Each mapper converts a gateway-agnostic spec dict into the specific
JSON structure expected by the webMethods Admin REST API.
"""

from typing import Any


def map_policy_to_webmethods(policy_spec: dict) -> dict:
    """Convert a STOA policy spec to a webMethods policy action + policy payload.

    Args:
        policy_spec: STOA-format policy with 'name', 'type', 'config' keys.

    Returns:
        dict with 'policyAction' and 'policy' payloads for webMethods REST API.
    """
    policy_type = policy_spec.get("type", "")
    config = policy_spec.get("config", {})
    name = policy_spec.get("name", "")

    type_mapping = {
        "cors": "corsPolicy",
        "rate_limit": "throttlingPolicy",
        "logging": "logInvocationPolicy",
        "jwt": "jwtPolicy",
        "ip_filter": "ipFilterPolicy",
    }

    wm_type = type_mapping.get(policy_type, policy_type)

    policy_action = {
        "policyActionName": name,
        "type": wm_type,
        "parameters": _map_policy_config(wm_type, config),
    }

    return {"policyAction": policy_action}


def _map_policy_config(wm_type: str, config: dict) -> dict:
    """Map STOA policy config to webMethods policyAction parameters."""
    if wm_type == "corsPolicy":
        return {
            "allowedOrigins": config.get("allowedOrigins", ["*"]),
            "allowedMethods": config.get("allowedMethods", ["GET"]),
            "allowedHeaders": config.get("allowedHeaders", []),
            "exposeHeaders": config.get("exposeHeaders", []),
            "maxAge": config.get("maxAge", 3600),
            "allowCredentials": config.get("allowCredentials", False),
        }
    elif wm_type == "throttlingPolicy":
        return {
            "maxRequestCount": config.get("maxRequests", 100),
            "intervalInSeconds": config.get("intervalSeconds", 60),
        }
    elif wm_type == "logInvocationPolicy":
        return {
            "logRequestPayload": config.get("logRequest", True),
            "logResponsePayload": config.get("logResponse", True),
        }
    return config


def map_alias_to_webmethods(alias_spec: dict) -> dict:
    """Convert a STOA alias spec to webMethods alias payload."""
    return {
        "name": alias_spec["name"],
        "description": alias_spec.get("description", ""),
        "type": alias_spec.get("type", "endpoint"),
        "endPointURI": alias_spec["endpointUri"],
        "connectionTimeout": alias_spec.get("connectionTimeout", 30),
        "readTimeout": alias_spec.get("readTimeout", 60),
        "optimizationTechnique": alias_spec.get("optimization", "None"),
        "passSecurityHeaders": alias_spec.get("passSecurityHeaders", True),
    }


def map_auth_server_to_webmethods(auth_spec: dict) -> dict:
    """Convert a STOA auth server spec to webMethods alias payload (type: authServerAlias)."""
    return {
        "name": auth_spec["name"],
        "description": auth_spec.get("description", ""),
        "type": "authServerAlias",
        "discoveryURL": auth_spec["discoveryURL"],
        "introspectionURL": auth_spec.get("introspectionURL", ""),
        "clientId": auth_spec["clientId"],
        "clientSecret": auth_spec.get("clientSecret", ""),
        "scopes": auth_spec.get("scopes", ["openid"]),
    }


def map_application_to_webmethods(app_spec: dict) -> dict:
    """Convert a STOA application spec to webMethods application payload."""
    return {
        "name": app_spec["name"],
        "description": app_spec.get("description", ""),
        "contactEmails": app_spec.get("contactEmails", []),
    }


def map_config_to_webmethods(config_spec: dict) -> dict[str, Any]:
    """Convert a STOA gateway config spec to webMethods configuration payloads.

    Returns a dict keyed by configuration endpoint path.
    """
    result = {}
    if "errorProcessing" in config_spec:
        result["errorProcessing"] = config_spec["errorProcessing"]
    if "callbackSettings" in config_spec:
        result["apiCallBackSettings"] = config_spec["callbackSettings"]
    if "keystore" in config_spec:
        result["keystore"] = config_spec["keystore"]
    if "jwt" in config_spec:
        result["jsonWebToken"] = config_spec["jwt"]
    return result
