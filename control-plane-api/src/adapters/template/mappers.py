"""Example mapper functions — adapt to your gateway's API format.

Mappers translate between STOA's internal data structures and your
gateway's admin API format. Every gateway has its own API contract;
these functions isolate the translation logic.
"""


def map_api_spec(api_spec: dict, tenant_id: str) -> dict:
    """Map STOA desired_state to your gateway's API creation format.

    Args:
        api_spec: Dict from GatewayDeployment.desired_state, containing:
            - spec_hash: SHA256 of the OpenAPI spec
            - version: API version string
            - api_name: Human-readable name
            - api_id: Unique identifier
            - tenant_id: Tenant owning this API
            - activated: Whether the API should accept traffic
        tenant_id: Tenant identifier

    Returns:
        Dict in your gateway's expected format for creating/updating an API.

    Example (for a hypothetical gateway):
        >>> map_api_spec({"api_name": "Payments", "version": "1.0"}, "acme")
        {"name": "Payments", "version": "1.0", "tags": ["tenant:acme"]}
    """
    return {
        "name": api_spec.get("api_name", ""),
        "version": api_spec.get("version", ""),
        # TODO: Map to your gateway's specific fields
        # "path_prefix": f"/apis/{tenant_id}/{api_spec.get('api_id', '')}",
        # "backend_url": api_spec.get("backend_url", ""),
        # "tags": [f"tenant:{tenant_id}"],
    }


def map_policy(policy_spec: dict) -> dict:
    """Map STOA policy to your gateway's policy format.

    Args:
        policy_spec: Dict containing:
            - name: Policy name
            - type: Policy type (cors, rate_limit, jwt_validation, etc.)
            - config: Gateway-agnostic policy configuration
            - priority: Execution priority (lower = first)
            - api_id: Gateway-side API resource ID

    Returns:
        Dict in your gateway's expected format for creating/updating a policy.
    """
    return {
        "name": policy_spec.get("name", ""),
        "type": policy_spec.get("type", ""),
        "config": policy_spec.get("config", {}),
        # TODO: Map to your gateway's specific policy format
    }


def map_api_from_gateway(gateway_api: dict) -> dict:
    """Map your gateway's API representation back to STOA format.

    Used by list_apis() to normalize gateway responses for drift detection.

    Args:
        gateway_api: Raw API object from your gateway's list endpoint.

    Returns:
        Dict with at minimum: id, name, spec_hash
    """
    return {
        "id": gateway_api.get("id", ""),
        "name": gateway_api.get("name", ""),
        "spec_hash": gateway_api.get("spec_hash", ""),
        # TODO: Map additional fields from your gateway's response
    }
