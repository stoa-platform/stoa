"""Remaining shared-key checks use the constant-time gateway key helper.

Covers gateway registration/heartbeat validation, the external MCP servers
internal listing and usage recording: valid key accepted, wrong or missing
key rejected, status codes unchanged.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.auth import gateway_key
from src.config import settings

VALID_KEY = "test-gateway-key"
USAGE_PAYLOAD = {"tenant_id": "acme", "subscription_id": "sub-1"}


def test_helper_compares_each_key_with_compare_digest():
    with patch.object(gateway_key.hmac, "compare_digest", wraps=gateway_key.hmac.compare_digest) as spy:
        assert gateway_key.gateway_key_is_valid(VALID_KEY, ["other-key", VALID_KEY])
    assert spy.call_count == 2


def test_helper_rejects_wrong_empty_and_missing_keys():
    assert not gateway_key.gateway_key_is_valid("test-gateway-kez", [VALID_KEY])
    assert not gateway_key.gateway_key_is_valid("", [VALID_KEY])
    assert not gateway_key.gateway_key_is_valid(None, [VALID_KEY])


# --- gateway_internal._validate_gateway_key ---


def test_validate_gateway_key_accepts_valid_key(monkeypatch):
    from src.routers.gateway_internal import _validate_gateway_key

    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", f"other-key,{VALID_KEY}")
    _validate_gateway_key(VALID_KEY)


@pytest.mark.parametrize("presented", ["not-the-key", ""])
def test_validate_gateway_key_rejects_invalid_key(monkeypatch, presented):
    from src.routers.gateway_internal import _validate_gateway_key

    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    with pytest.raises(HTTPException) as exc:
        _validate_gateway_key(presented)
    assert exc.value.status_code == 401


def test_validate_gateway_key_without_configured_keys_is_503(monkeypatch):
    from src.routers.gateway_internal import _validate_gateway_key

    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
    with pytest.raises(HTTPException) as exc:
        _validate_gateway_key(VALID_KEY)
    assert exc.value.status_code == 503


# --- GET /v1/internal/external-mcp-servers ---


@pytest.fixture
def mcp_backend():
    repo = MagicMock()
    repo.list_enabled_with_tools = AsyncMock(return_value=[])
    with (
        patch("src.routers.external_mcp_servers.ExternalMCPServerRepository", return_value=repo),
        patch("src.routers.external_mcp_servers.get_vault_client", return_value=MagicMock()),
    ):
        yield


def test_external_mcp_internal_accepts_valid_key(client, mcp_backend, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", f"other-key,{VALID_KEY}")
    resp = client.get("/v1/internal/external-mcp-servers", headers={"X-Gateway-Key": VALID_KEY})
    assert resp.status_code == 200


@pytest.mark.parametrize("presented", ["not-the-key", ""])
def test_external_mcp_internal_rejects_invalid_key(client, mcp_backend, monkeypatch, presented):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    resp = client.get("/v1/internal/external-mcp-servers", headers={"X-Gateway-Key": presented})
    assert resp.status_code == 401


def test_external_mcp_internal_without_configured_keys_is_503(client, mcp_backend, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
    resp = client.get("/v1/internal/external-mcp-servers", headers={"X-Gateway-Key": VALID_KEY})
    assert resp.status_code == 503


# --- POST /v1/usage/record ---


@pytest.fixture
def usage_backend():
    service = MagicMock()
    service.record_usage = AsyncMock(return_value=None)
    with patch("src.routers.usage_metering.UsageMeteringService", return_value=service):
        yield service


def test_usage_record_accepts_valid_key(client, usage_backend, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", f"other-key,{VALID_KEY}")
    resp = client.post("/v1/usage/record", json=USAGE_PAYLOAD, headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 201
    usage_backend.record_usage.assert_awaited_once()


@pytest.mark.parametrize("presented", ["not-the-key", ""])
def test_usage_record_rejects_invalid_key(client, usage_backend, monkeypatch, presented):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    resp = client.post("/v1/usage/record", json=USAGE_PAYLOAD, headers={"X-API-Key": presented})
    assert resp.status_code == 401
    usage_backend.record_usage.assert_not_awaited()


def test_usage_record_without_configured_keys_is_401(client, usage_backend, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
    resp = client.post("/v1/usage/record", json=USAGE_PAYLOAD, headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 401
