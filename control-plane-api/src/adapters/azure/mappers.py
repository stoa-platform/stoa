"""Mappers between Control Plane spec and Azure API Management native format.

Azure APIM REST API reference:
  https://learn.microsoft.com/en-us/rest/api/apimanagement/

Key concepts:
  - APIs: REST/SOAP APIs registered in the APIM instance
  - Products: bundles of APIs with rate-limit / quota policies
  - Subscriptions: consumer access keys scoped to a product or API
"""


def map_api_spec_to_azure(api_spec: dict, tenant_id: str) -> dict:
    """Map CP API spec to Azure APIM API creation payload.

    Args:
        api_spec: Control Plane API specification dict.
        tenant_id: Tenant owning this API.

    Returns:
        Dict suitable for PUT /apis/{apiId} call.
    """
    name = api_spec.get("name", "unnamed-api")
    api_id = f"stoa-{tenant_id}-{name}".replace(" ", "-").lower()
    backend_url = api_spec.get("backend_url", "https://httpbin.org")
    api_path = api_spec.get("path", f"/{name}")

    return {
        "properties": {
            "displayName": api_spec.get("display_name", name),
            "description": api_spec.get("description", ""),
            "path": api_path,
            "protocols": api_spec.get("protocols", ["https"]),
            "serviceUrl": backend_url,
        },
        "_stoa_api_id": api_id,
        "_stoa_metadata": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-api-id": api_spec.get("id", ""),
            "stoa-api-name": name,
        },
    }


def map_azure_api_to_cp(api: dict) -> dict:
    """Map Azure APIM API response to CP format.

    Args:
        api: Azure APIM API dict from GET /apis response.

    Returns:
        Normalized CP API dict.
    """
    props = api.get("properties", {})
    # Extract STOA ID from the API name convention (stoa-{tenant}-{name})
    api_name = api.get("name", "")

    return {
        "id": api_name,
        "name": props.get("displayName", api_name),
        "display_name": props.get("displayName", api_name),
        "description": props.get("description", ""),
        "gateway_resource_id": api.get("id", ""),
        "gateway_type": "azure_apim",
        "path": props.get("path", ""),
        "service_url": props.get("serviceUrl", ""),
    }


def map_policy_to_azure_product(policy_spec: dict, tenant_id: str) -> dict:
    """Map CP policy spec to Azure APIM Product creation payload.

    Azure Products bundle APIs with subscription-level rate limiting.
    Rate-limit policies are applied via XML policy on the product scope.

    Args:
        policy_spec: CP policy spec (type=rate_limit).
        tenant_id: Tenant identifier.

    Returns:
        Dict suitable for PUT /products/{productId} call.
    """
    policy_id = policy_spec.get("id", "")
    config = policy_spec.get("config", {})
    max_requests = config.get("max_requests", 100)
    window_seconds = config.get("window_seconds", 60)

    product_id = f"stoa-{policy_id}"

    return {
        "_stoa_product_id": product_id,
        "properties": {
            "displayName": policy_spec.get("name", product_id),
            "description": policy_spec.get("description", f"Rate limit: {max_requests}/{window_seconds}s"),
            "subscriptionRequired": True,
            "approvalRequired": False,
            "state": "published",
        },
        "_stoa_rate_limit": {
            "calls": max_requests,
            "renewal_period": window_seconds,
        },
        "_stoa_metadata": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-policy-id": policy_id,
        },
    }


def map_azure_product_to_policy(product: dict) -> dict:
    """Map Azure APIM Product back to CP policy format.

    Args:
        product: Azure product dict from GET /products response.

    Returns:
        Normalized CP policy dict.
    """
    props = product.get("properties", {})
    product_name = product.get("name", "")

    # Extract policy ID from product name convention (stoa-{policy_id})
    policy_id = product_name
    if product_name.startswith("stoa-"):
        policy_id = product_name[5:]

    return {
        "id": policy_id,
        "name": props.get("displayName", product_name),
        "description": props.get("description", ""),
        "type": "rate_limit",
        "gateway_type": "azure_apim",
        "gateway_resource_id": product.get("id", ""),
    }


def map_app_spec_to_azure_subscription(app_spec: dict, tenant_id: str) -> dict:
    """Map CP application spec to Azure APIM Subscription creation payload.

    Args:
        app_spec: CP application specification dict.
        tenant_id: Tenant identifier.

    Returns:
        Dict suitable for PUT /subscriptions/{sid} call.
    """
    app_id = app_spec.get("id", "")
    name = app_spec.get("name", f"stoa-app-{app_id}")
    subscription_name = f"stoa-{tenant_id}-{name}".replace(" ", "-").lower()

    return {
        "_stoa_subscription_name": subscription_name,
        "properties": {
            "displayName": name,
            "scope": app_spec.get("scope", ""),
            "state": "active",
        },
        "_stoa_metadata": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-app-id": app_id,
            "stoa-subscription-id": app_spec.get("subscription_id", ""),
        },
    }


def map_azure_subscription_to_cp(sub: dict) -> dict:
    """Map Azure APIM Subscription back to CP application format.

    Args:
        sub: Azure subscription dict from GET /subscriptions response.

    Returns:
        Normalized CP application dict.
    """
    props = sub.get("properties", {})
    sub_name = sub.get("name", "")

    return {
        "id": sub_name,
        "name": props.get("displayName", sub_name),
        "description": "",
        "subscription_id": sub_name,
        "gateway_resource_id": sub.get("id", ""),
        "gateway_type": "azure_apim",
        "state": props.get("state", ""),
        "created_at": props.get("createdDate"),
    }


def build_rate_limit_policy_xml(calls: int, renewal_period: int) -> str:
    """Build Azure APIM rate-limit policy XML fragment.

    Args:
        calls: Maximum number of calls in the renewal period.
        renewal_period: Period in seconds.

    Returns:
        XML policy string for the product scope.
    """
    return (
        "<policies>"
        "<inbound>"
        "<base />"
        f'<rate-limit calls="{calls}" renewal-period="{renewal_period}" />'
        "</inbound>"
        "<backend><base /></backend>"
        "<outbound><base /></outbound>"
        "<on-error><base /></on-error>"
        "</policies>"
    )
