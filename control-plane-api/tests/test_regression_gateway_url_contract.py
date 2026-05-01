from datetime import UTC, datetime
from uuid import uuid4

from src.schemas.gateway import GatewayInstanceResponse
from src.services.gateway_topology import build_endpoints, endpoint_value


def _gateway_payload(**overrides):
    now = datetime(2026, 5, 1, tzinfo=UTC)
    payload = {
        "id": uuid4(),
        "name": "stoa-link-wm-prod-sidecar-production",
        "display_name": "STOA Link webMethods",
        "gateway_type": "stoa_sidecar",
        "environment": "production",
        "tenant_id": None,
        "base_url": "http://stoa-link-wm.stoa-dataplane.svc.cluster.local:8080",
        "target_gateway_url": None,
        "public_url": None,
        "ui_url": None,
        "endpoints": {},
        "deployment_mode": None,
        "target_gateway_type": None,
        "topology": None,
        "auth_config": {},
        "status": "online",
        "last_health_check": now,
        "health_details": {},
        "capabilities": [],
        "version": "0.1.0",
        "tags": ["mode:sidecar"],
        "mode": "sidecar",
        "protected": False,
        "enabled": True,
        "visibility": None,
        "source": "self_register",
        "deleted_at": None,
        "deleted_by": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return payload


def test_endpoint_aliases_are_exposed_as_canonical_urls():
    endpoints = build_endpoints(
        endpoints={
            "publicUrl": "https://runtime.example.com",
            "uiUrl": "https://ui.example.com",
            "targetGatewayUrl": "https://target.example.com",
        },
        base_url="http://gateway.stoa-system.svc.cluster.local:8080",
    )

    assert endpoint_value(endpoints, "public_url") == "https://runtime.example.com"
    assert endpoint_value(endpoints, "ui_url") == "https://ui.example.com"
    assert endpoint_value(endpoints, "target_gateway_url") == "https://target.example.com"
    assert endpoints["internal_url"] == "http://gateway.stoa-system.svc.cluster.local:8080"


def test_gateway_response_backfills_top_level_urls_from_endpoints():
    gateway = GatewayInstanceResponse.model_validate(
        _gateway_payload(
            endpoints={
                "publicUrl": "https://wm-runtime.gostoa.dev",
                "uiUrl": "https://wm-ui.gostoa.dev",
                "targetGatewayUrl": "https://vps-wm.gostoa.dev",
            }
        )
    )

    assert gateway.public_url == "https://wm-runtime.gostoa.dev"
    assert gateway.ui_url == "https://wm-ui.gostoa.dev"
    assert gateway.target_gateway_url == "https://vps-wm.gostoa.dev"
    assert gateway.endpoints["public_url"] == "https://wm-runtime.gostoa.dev"
    assert gateway.endpoints["ui_url"] == "https://wm-ui.gostoa.dev"
    assert gateway.endpoints["target_gateway_url"] == "https://vps-wm.gostoa.dev"


def test_top_level_urls_override_stale_endpoint_values():
    gateway = GatewayInstanceResponse.model_validate(
        _gateway_payload(
            public_url="https://wm-runtime.gostoa.dev",
            ui_url="https://wm-ui.gostoa.dev",
            endpoints={
                "public_url": "https://stale-runtime.gostoa.dev",
                "ui_url": "https://stale-ui.gostoa.dev",
            },
        )
    )

    assert gateway.public_url == "https://wm-runtime.gostoa.dev"
    assert gateway.ui_url == "https://wm-ui.gostoa.dev"
    assert gateway.endpoints["public_url"] == "https://wm-runtime.gostoa.dev"
    assert gateway.endpoints["ui_url"] == "https://wm-ui.gostoa.dev"
