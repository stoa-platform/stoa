"""
Tests for Token Exchange endpoint (RFC 8693) — CAB-1121 Session 3

Tests: 10 test cases covering happy path, validation errors,
consumer state checks, and Keycloak error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient


class TestTokenExchange:
    """Test suite for POST /v1/consumers/{tenant_id}/{consumer_id}/token-exchange."""

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        """Create a mock Consumer object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== Happy Path ==============

    def test_exchange_token_success(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test successful token exchange returns 200 with new token."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        kc_client = {"id": "kc-uuid-123", "clientId": "acme-partner-acme-001"}
        kc_secret = {"value": "client-secret-123"}
        exchange_result = {
            "access_token": "exchanged-token-xyz",
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": "openid",
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(return_value=kc_client)
            mock_kc._admin.get_client_secrets.return_value = kc_secret
            mock_kc.exchange_token = AsyncMock(return_value=exchange_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={
                        "subject_token": "original-access-token",
                        "audience": "stoa-api",
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "exchanged-token-xyz"
            assert data["token_type"] == "Bearer"
            assert data["expires_in"] == 300
            assert data["scope"] == "openid"

            # Verify exchange_token was called with correct params
            mock_kc.exchange_token.assert_awaited_once()
            call_kwargs = mock_kc.exchange_token.call_args.kwargs
            assert call_kwargs["client_id"] == "acme-partner-acme-001"
            assert call_kwargs["subject_token"] == "original-access-token"
            assert call_kwargs["audience"] == "stoa-api"
            assert call_kwargs["scope"] is None

    def test_exchange_token_with_scope(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange with custom scope parameter."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        kc_client = {"id": "kc-uuid-123", "clientId": "acme-partner-acme-001"}
        kc_secret = {"value": "secret"}
        exchange_result = {
            "access_token": "scoped-token",
            "token_type": "Bearer",
            "expires_in": 600,
            "scope": "read:apis",
        }

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(return_value=kc_client)
            mock_kc._admin.get_client_secrets.return_value = kc_secret
            mock_kc.exchange_token = AsyncMock(return_value=exchange_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={
                        "subject_token": "my-token",
                        "scope": "read:apis",
                    },
                )

            assert response.status_code == 200
            assert response.json()["scope"] == "read:apis"

    # ============== Consumer Not Found ==============

    def test_exchange_token_consumer_not_found(self, app_with_tenant_admin, mock_db_session):
        """Test token exchange with non-existent consumer returns 404."""
        fake_id = uuid4()

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{fake_id}/token-exchange",
                    json={"subject_token": "some-token"},
                )

            assert response.status_code == 404
            assert "Consumer not found" in response.json()["detail"]

    # ============== Consumer Suspended ==============

    def test_exchange_token_consumer_suspended(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange with suspended consumer returns 400."""
        consumer_data = {
            **sample_consumer_data,
            "status": "suspended",
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={"subject_token": "some-token"},
                )

            assert response.status_code == 400
            assert "active" in response.json()["detail"].lower()

    # ============== No Keycloak Client ==============

    def test_exchange_token_no_keycloak_client(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange when consumer has no Keycloak client returns 404."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": None,
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={"subject_token": "some-token"},
                )

            assert response.status_code == 404
            assert "Keycloak client" in response.json()["detail"]

    # ============== Tenant Isolation ==============

    def test_exchange_token_wrong_tenant(self, app_with_other_tenant, mock_db_session, sample_consumer_data):
        """Test token exchange denied for wrong tenant returns 403."""
        with TestClient(app_with_other_tenant) as client:
            response = client.post(
                f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                json={"subject_token": "some-token"},
            )

        assert response.status_code == 403

    # ============== Keycloak Unavailable ==============

    def test_exchange_token_keycloak_unavailable(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange when Keycloak is down returns 503."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(side_effect=RuntimeError("Connection refused"))

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={"subject_token": "some-token"},
                )

            assert response.status_code == 503
            assert "Retry-After" in response.headers

    # ============== Invalid Subject Token ==============

    def test_exchange_token_invalid_subject_token(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange with invalid subject token returns 401."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        kc_client = {"id": "kc-uuid-123", "clientId": "acme-partner-acme-001"}
        kc_secret = {"value": "secret"}

        # Simulate Keycloak 400 response for invalid token
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "invalid subject token",
        }
        kc_error = httpx.HTTPStatusError("Bad Request", request=MagicMock(), response=mock_response)

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(return_value=kc_client)
            mock_kc._admin.get_client_secrets.return_value = kc_secret
            mock_kc.exchange_token = AsyncMock(side_effect=kc_error)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={"subject_token": "invalid-token"},
                )

            assert response.status_code == 401
            assert "invalid subject token" in response.json()["detail"]

    # ============== CPI-Admin Cross-Tenant Access ==============

    def test_exchange_token_cpi_admin_any_tenant(self, app_with_cpi_admin, mock_db_session, sample_consumer_data):
        """Test CPI-admin can exchange tokens for any tenant's consumer."""
        consumer_data = {
            **sample_consumer_data,
            "keycloak_client_id": "acme-partner-acme-001",
        }
        mock_consumer = self._create_mock_consumer(consumer_data)

        kc_client = {"id": "kc-uuid", "clientId": "acme-partner-acme-001"}
        kc_secret = {"value": "secret"}
        exchange_result = {
            "access_token": "admin-exchanged-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }

        with (
            patch("src.routers.consumers.ConsumerRepository") as MockRepo,
            patch("src.routers.consumers.keycloak_service") as mock_kc,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(return_value=kc_client)
            mock_kc._admin.get_client_secrets.return_value = kc_secret
            mock_kc.exchange_token = AsyncMock(return_value=exchange_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                    json={"subject_token": "admin-token"},
                )

            assert response.status_code == 200
            assert response.json()["access_token"] == "admin-exchanged-token"

    # ============== Missing Subject Token ==============

    def test_exchange_token_missing_subject_token(self, app_with_tenant_admin, mock_db_session, sample_consumer_data):
        """Test token exchange with empty body returns 422."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                f"/v1/consumers/acme/{sample_consumer_data['id']}/token-exchange",
                json={},
            )

        assert response.status_code == 422
