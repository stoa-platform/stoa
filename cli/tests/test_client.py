"""Tests for the StoaClient API client."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.client import StoaClient
from src.config import Credentials, StoaConfig


@pytest.fixture()
def client(sample_config: StoaConfig, sample_credentials: Credentials) -> StoaClient:
    return StoaClient(config=sample_config, credentials=sample_credentials)


@pytest.fixture()
def expired_client(
    sample_config: StoaConfig, expired_credentials: Credentials
) -> StoaClient:
    return StoaClient(config=sample_config, credentials=expired_credentials)


class TestEnsureToken:
    def test_valid_token_returned(self, client: StoaClient):
        token = client._ensure_token()
        assert token == client.credentials.access_token

    def test_no_token_raises(self, sample_config: StoaConfig):
        c = StoaClient(config=sample_config, credentials=Credentials())
        with pytest.raises(RuntimeError, match="Not authenticated"):
            c._ensure_token()

    def test_expired_token_triggers_refresh(self, expired_client: StoaClient):
        with patch("src.client.refresh_token") as mock_refresh:
            new_creds = Credentials(
                access_token="new-token",
                refresh_token="new-ref",
                expires_at=time.time() + 3600,
            )
            mock_refresh.return_value = new_creds
            token = expired_client._ensure_token()
        assert token == "new-token"


class TestHealth:
    def test_health_ok(self, client: StoaClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "version": "2.0.0"}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            mock_cls.return_value = mock_http

            health = client.health()

        assert health.status == "ok"
        assert health.version == "2.0.0"


class TestListAPIs:
    def test_list_apis_returns_models(self, client: StoaClient):
        api_data = [
            {
                "id": "api-1",
                "name": "weather",
                "display_name": "Weather API",
                "version": "1.0.0",
                "status": "active",
            },
            {
                "id": "api-2",
                "name": "payments",
                "display_name": "Payments API",
                "version": "2.0.0",
                "status": "draft",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = api_data
        mock_resp.raise_for_status = MagicMock()

        with patch("src.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            mock_cls.return_value = mock_http

            apis = client.list_apis(tenant_id="acme")

        assert len(apis) == 2
        assert apis[0].name == "weather"
        assert apis[1].status == "draft"

    def test_list_apis_dict_response(self, client: StoaClient):
        """API might return {apis: [...]} wrapper."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "apis": [
                {"id": "1", "name": "a", "display_name": "A", "version": "1.0"}
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("src.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            mock_cls.return_value = mock_http

            apis = client.list_apis(tenant_id="acme")

        assert len(apis) == 1


class TestGetAPI:
    def test_get_api_by_name(self, client: StoaClient):
        with patch.object(client, "list_apis") as mock_list:
            from src.models import APIResponse

            mock_list.return_value = [
                APIResponse(id="1", name="weather", display_name="Weather", version="1.0"),
                APIResponse(id="2", name="payments", display_name="Pay", version="2.0"),
            ]
            api = client.get_api("weather")
        assert api.name == "weather"

    def test_get_api_by_id(self, client: StoaClient):
        with patch.object(client, "list_apis") as mock_list:
            from src.models import APIResponse

            mock_list.return_value = [
                APIResponse(id="abc-123", name="weather", display_name="W", version="1.0"),
            ]
            api = client.get_api("abc-123")
        assert api.id == "abc-123"

    def test_get_api_not_found(self, client: StoaClient):
        with patch.object(client, "list_apis") as mock_list:
            mock_list.return_value = []
            with pytest.raises(RuntimeError, match="not found"):
                client.get_api("nonexistent")


class TestCreateAPI:
    def test_create_api(self, client: StoaClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "new-api", "name": "test"}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.client.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_resp
            mock_cls.return_value = mock_http

            result = client.create_api({"name": "test"}, tenant_id="acme")

        assert result["id"] == "new-api"


class TestTenantResolution:
    def test_tenant_from_config(self, client: StoaClient):
        assert client._tenant_id() == "acme"

    def test_tenant_from_claims(self, sample_config: StoaConfig):
        sample_config.tenant_id = None
        creds = Credentials(
            access_token="tok",
            expires_at=time.time() + 3600,
            claims={"tenant_id": "from-claims"},
        )
        c = StoaClient(config=sample_config, credentials=creds)
        assert c._tenant_id() == "from-claims"

    def test_tenant_from_claims_list(self, sample_config: StoaConfig):
        sample_config.tenant_id = None
        creds = Credentials(
            access_token="tok",
            expires_at=time.time() + 3600,
            claims={"tenant_id": ["t1", "t2"]},
        )
        c = StoaClient(config=sample_config, credentials=creds)
        assert c._tenant_id() == "t1"
