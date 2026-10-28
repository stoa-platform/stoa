"""A request without the shared-key header is rejected by FastAPI with 422
before any key comparison runs, on each of the three endpoints that
authenticate a gateway with a configured shared key:

- ``POST /v1/internal/gateways/cleanup`` (``X-Gateway-Key``, ``gateway_internal.py``)
- ``GET /v1/internal/external-mcp-servers`` (``X-Gateway-Key``, ``external_mcp_servers.py``)
- ``POST /v1/usage/record`` (``X-API-Key``, ``usage_metering.py``)

The header is declared ``Header(...)`` (required) on all three routes; this
pins that a missing header never reaches the comparison (no 401, no 503, no
500) whether or not keys are configured.
"""

from __future__ import annotations

import pytest


@pytest.fixture(params=["configured", "not-configured"])
def gateway_keys_state(request, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "test-gateway-key" if request.param == "configured" else "")
    return request.param


def test_gateway_internal_cleanup_without_header_is_422(client, gateway_keys_state):
    resp = client.post("/v1/internal/gateways/cleanup")
    assert resp.status_code == 422
    assert any(e.get("loc") == ["header", "X-Gateway-Key"] for e in resp.json()["detail"])


def test_external_mcp_servers_without_header_is_422(client, gateway_keys_state):
    resp = client.get("/v1/internal/external-mcp-servers")
    assert resp.status_code == 422
    assert any(e.get("loc") == ["header", "X-Gateway-Key"] for e in resp.json()["detail"])


def test_usage_record_without_header_is_422(client, gateway_keys_state):
    resp = client.post("/v1/usage/record", json={})
    assert resp.status_code == 422
    assert any(e.get("loc") == ["header", "X-API-Key"] for e in resp.json()["detail"])
