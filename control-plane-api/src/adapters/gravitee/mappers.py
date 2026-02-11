"""Mappers: translate Control Plane specs to Gravitee Management API v2 format."""


def map_api_spec_to_gravitee_v4(api_spec: dict, tenant_id: str) -> dict:
    """Map CP api_spec to a Gravitee v4 API definition.

    Ref: https://docs.gravitee.io/apim/3.x/apim_publisherguide_manage_apis.html
    """
    api_name = api_spec.get("api_name", api_spec.get("apiName", "unknown"))
    backend_url = api_spec.get("backend_url", api_spec.get("url", ""))

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
