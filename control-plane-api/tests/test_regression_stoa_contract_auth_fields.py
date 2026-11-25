"""Regression tests: caller authentication fields forwarded to stoa-gateway contracts."""

import json

from src.adapters.stoa.mappers import map_uac_to_stoa_contract

BASE_SPEC = {
    "name": "orders",
    "version": "2.1.0",
    "tenant_id": "acme",
    "display_name": "Orders",
    "description": "Order API",
    "classification": "VH",
    "endpoints": [
        {
            "path": "/orders",
            "methods": ["GET"],
            "backend_url": "https://backend.example.com/orders",
            "operation_id": "list_orders",
            "input_schema": {"type": "object"},
            "output_schema": None,
            "ignored": "value",
        }
    ],
    "required_policies": ["auth-jwt"],
    "status": "published",
    "source_spec_url": "https://specs.example.com/orders.yaml",
    "spec_hash": "abc123",
}

AUTH_KEYS = ("inbound_auth", "inbound_auth_audience", "public")


def test_regression_contract_mapping_inbound_auth_forwarded():
    payload = map_uac_to_stoa_contract({**BASE_SPEC, "inbound_auth": " jwt ", "inbound_auth_audience": "orders-api"})
    assert payload["inbound_auth"] == "jwt"
    assert payload["inbound_auth_audience"] == "orders-api"
    assert "public" not in payload


def test_regression_contract_mapping_inbound_auth_aliases_forwarded():
    payload = map_uac_to_stoa_contract({**BASE_SPEC, "inboundAuth": "oauth2", "inboundAuthAudience": "orders-api"})
    assert payload["inbound_auth"] == "oauth2"
    assert payload["inbound_auth_audience"] == "orders-api"
    assert "inboundAuth" not in payload


def test_regression_contract_mapping_public_forwarded():
    payload = map_uac_to_stoa_contract({**BASE_SPEC, "public": True})
    assert payload["public"] is True
    assert "inbound_auth" not in payload


def test_regression_contract_mapping_public_absent_by_default():
    payload = map_uac_to_stoa_contract(BASE_SPEC)
    for key in AUTH_KEYS:
        assert key not in payload


def test_regression_contract_mapping_public_only_sent_when_true():
    for value in (False, None, "true", 1, "yes"):
        payload = map_uac_to_stoa_contract({**BASE_SPEC, "public": value})
        assert "public" not in payload, value


def test_regression_contract_mapping_empty_auth_values_not_sent():
    for value in (None, "", "   ", 42):
        payload = map_uac_to_stoa_contract({**BASE_SPEC, "inbound_auth": value, "inbound_auth_audience": value})
        assert "inbound_auth" not in payload
        assert "inbound_auth_audience" not in payload


def test_regression_contract_mapping_existing_fields_unchanged():
    payload = map_uac_to_stoa_contract(BASE_SPEC)
    assert payload == {
        "name": "orders",
        "version": "2.1.0",
        "tenant_id": "acme",
        "display_name": "Orders",
        "description": "Order API",
        "classification": "VH",
        "endpoints": [
            {
                "path": "/orders",
                "methods": ["GET"],
                "backend_url": "https://backend.example.com/orders",
                "operation_id": "list_orders",
                "input_schema": {"type": "object"},
                "output_schema": None,
            }
        ],
        "required_policies": ["auth-jwt"],
        "status": "published",
        "source_spec_url": "https://specs.example.com/orders.yaml",
        "spec_hash": "abc123",
    }


def test_regression_contract_mapping_minimal_spec_defaults_unchanged():
    payload = map_uac_to_stoa_contract({"name": "orders", "version": "1.0.0", "tenant_id": "acme", "endpoints": []})
    assert payload == {
        "name": "orders",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": None,
        "description": None,
        "classification": "H",
        "endpoints": [],
        "required_policies": [],
        "status": "draft",
        "source_spec_url": None,
        "spec_hash": None,
    }


def test_regression_contract_mapping_payload_never_carries_null_public():
    # The gateway reads `public` as a boolean: a JSON null must never be sent.
    for spec in (BASE_SPEC, {**BASE_SPEC, "public": None}, {**BASE_SPEC, "public": True}):
        encoded = json.loads(json.dumps(map_uac_to_stoa_contract(spec)))
        assert encoded.get("public", False) in (True, False)
        assert "public" not in encoded or encoded["public"] is True
