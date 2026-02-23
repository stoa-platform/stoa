"""Mappers between Control Plane spec and Apigee X native format."""


def map_api_spec_to_apigee_proxy(api_spec: dict, tenant_id: str) -> dict:
    """Map CP API spec to Apigee API proxy bundle metadata."""
    name = api_spec.get("name", "unnamed-api")
    safe_name = f"stoa-{tenant_id}-{name}".replace(" ", "-").lower()

    return {
        "name": safe_name,
        "displayName": api_spec.get("display_name", name),
        "description": api_spec.get("description", ""),
        "basePath": api_spec.get("base_path", f"/{name}"),
        "targetUrl": api_spec.get("target_url", ""),
        "labels": {
            "stoa-managed": "true",
            "stoa-tenant": tenant_id,
            "stoa-api-id": api_spec.get("id", ""),
        },
    }


def map_apigee_proxy_to_cp(proxy: dict) -> dict:
    """Map Apigee API proxy to CP format."""
    labels = proxy.get("labels", {})
    meta = proxy.get("metaData", {})

    return {
        "id": labels.get("stoa-api-id", proxy.get("name", "")),
        "name": proxy.get("name", ""),
        "display_name": proxy.get("displayName", proxy.get("name", "")),
        "description": proxy.get("description", ""),
        "base_path": proxy.get("basePath", ""),
        "target_url": "",
        "gateway_type": "apigee",
        "created_at": meta.get("createdAt"),
        "updated_at": meta.get("lastModifiedAt"),
    }


def map_policy_to_apigee_product(policy_spec: dict, tenant_id: str) -> dict:
    """Map CP policy spec to Apigee API product."""
    policy_id = policy_spec.get("id", "")
    policy_type = policy_spec.get("type", "rate_limit")
    name = f"stoa-{policy_type}-{policy_id}"

    product: dict = {
        "name": name,
        "displayName": policy_spec.get("name", name),
        "description": policy_spec.get("description", ""),
        "approvalType": "auto",
        "attributes": [
            {"name": "stoa-managed", "value": "true"},
            {"name": "stoa-tenant", "value": tenant_id},
            {"name": "stoa-policy-id", "value": policy_id},
        ],
    }

    if policy_type == "rate_limit":
        config = policy_spec.get("config", {})
        quota = config.get("max_requests", 100)
        interval = config.get("window_seconds", 60)
        product["quota"] = str(quota)
        product["quotaInterval"] = str(interval)
        product["quotaTimeUnit"] = "second" if interval <= 1 else "minute"

    return product


def map_apigee_product_to_policy(product: dict) -> dict:
    """Map Apigee API product back to CP policy format."""
    attrs = {a["name"]: a["value"] for a in product.get("attributes", [])}

    policy: dict = {
        "id": attrs.get("stoa-policy-id", product.get("name", "")),
        "name": product.get("displayName", product.get("name", "")),
        "description": product.get("description", ""),
        "type": "rate_limit",
        "gateway_type": "apigee",
    }

    if product.get("quota"):
        policy["config"] = {
            "max_requests": int(product["quota"]),
            "window_seconds": int(product.get("quotaInterval", "60")),
        }

    return policy


# --- Application Mappers (Developer Apps) ---


def map_app_spec_to_apigee_developer_app(app_spec: dict, tenant_id: str) -> dict:
    """Map CP application spec to Apigee Developer App payload."""
    app_id = app_spec.get("id", "")
    name = f"stoa-{tenant_id}-{app_id}".replace(" ", "-").lower()

    app: dict = {
        "name": name,
        "attributes": [
            {"name": "stoa-managed", "value": "true"},
            {"name": "stoa-tenant", "value": tenant_id},
            {"name": "stoa-app-id", "value": app_id},
            {"name": "DisplayName", "value": app_spec.get("name", name)},
        ],
    }

    # Bind to API products (policy IDs)
    api_products = app_spec.get("api_products", [])
    if api_products:
        app["apiProducts"] = api_products

    return app


def map_apigee_developer_app_to_cp(app: dict) -> dict:
    """Map Apigee Developer App to CP application format."""
    attrs = {a["name"]: a["value"] for a in app.get("attributes", [])}

    # Extract API key from credentials
    api_key = ""
    credentials = app.get("credentials", [])
    if credentials:
        api_key = credentials[0].get("consumerKey", "")

    return {
        "id": attrs.get("stoa-app-id", app.get("appId", "")),
        "name": attrs.get("DisplayName", app.get("name", "")),
        "gateway_app_id": app.get("name", ""),
        "api_key": api_key,
        "tenant_id": attrs.get("stoa-tenant", ""),
        "gateway_type": "apigee",
        "status": app.get("status", "approved"),
        "created_at": app.get("createdAt"),
        "updated_at": app.get("lastModifiedAt"),
    }
