"""
Tests for Consumer Keycloak Integration — CAB-1121 Phase 2

Target: Keycloak client creation on activation, credentials endpoint, 503 handling
Tests: 11 test cases
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestCreateConsumerKeycloak:
    """Test Keycloak client creation during consumer creation."""

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def test_create_consumer_creates_keycloak_client(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test that creating an active consumer triggers Keycloak client creation."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.keycloak_client_id = None

        updated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": "acme-partner-acme-001"}
        )

        kc_result = {
            "client_id": "acme-partner-acme-001",
            "client_secret": "generated-secret-123",
            "id": "kc-uuid-456",
        }

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_external_id = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=mock_consumer)
            mock_repo.update = AsyncMock(return_value=updated_consumer)
            mock_kc.create_consumer_client = AsyncMock(return_value=kc_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "ACME Corp",
                        "email": "api@acme.com",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["keycloak_client_id"] == "acme-partner-acme-001"

            mock_kc.create_consumer_client.assert_awaited_once_with(
                tenant_slug="acme",
                consumer_external_id="partner-acme-001",
                consumer_id=str(sample_consumer_data["id"]),
            )

    def test_create_consumer_keycloak_unavailable_503(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test 503 with Retry-After when Keycloak is unreachable during creation."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.keycloak_client_id = None

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_external_id = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=mock_consumer)
            mock_kc.create_consumer_client = AsyncMock(
                side_effect=RuntimeError("Keycloak not connected")
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "ACME Corp",
                        "email": "api@acme.com",
                    },
                )

            assert response.status_code == 503
            assert response.headers.get("retry-after") == "5"
            assert "unavailable" in response.json()["detail"].lower()


class TestActivateConsumerKeycloak:
    """Test Keycloak client creation during consumer activation."""

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def test_activate_creates_keycloak_client(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test that activating a suspended consumer creates a Keycloak client."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended", "keycloak_client_id": None}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        activated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "active", "keycloak_client_id": "acme-partner-acme-001"}
        )

        kc_result = {
            "client_id": "acme-partner-acme-001",
            "client_secret": "secret-123",
            "id": "kc-uuid-456",
        }

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo.update_status = AsyncMock(return_value=mock_consumer)
            mock_repo.update = AsyncMock(return_value=activated_consumer)
            # After update_status, keycloak_client_id is still None
            mock_consumer.keycloak_client_id = None
            mock_kc.create_consumer_client = AsyncMock(return_value=kc_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/activate"
                )

            assert response.status_code == 200
            mock_kc.create_consumer_client.assert_awaited_once()

    def test_activate_keycloak_unavailable_503(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test 503 when Keycloak is down during activation."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended", "keycloak_client_id": None}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo.update_status = AsyncMock(return_value=mock_consumer)
            mock_consumer.keycloak_client_id = None
            mock_kc.create_consumer_client = AsyncMock(
                side_effect=RuntimeError("Keycloak not connected")
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/activate"
                )

            assert response.status_code == 503
            assert response.headers.get("retry-after") == "5"

    def test_activate_skips_keycloak_if_client_exists(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test activation skips Keycloak client creation if already present."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended", "keycloak_client_id": "acme-existing"}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        activated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "active", "keycloak_client_id": "acme-existing"}
        )

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo.update_status = AsyncMock(return_value=activated_consumer)

            mock_kc.create_consumer_client = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/activate"
                )

            assert response.status_code == 200
            mock_kc.create_consumer_client.assert_not_awaited()


class TestConsumerCredentials:
    """Test GET /consumers/{tenant_id}/{consumer_id}/credentials endpoint."""

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def test_get_credentials_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test successful one-time credential retrieval."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": "acme-partner-acme-001"}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "active"
        mock_consumer.status.value = "active"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "active"

        mock_kc_client = {"id": "kc-uuid-789", "clientId": "acme-partner-acme-001"}

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(return_value=mock_kc_client)
            mock_kc._admin = MagicMock()
            mock_kc._admin.generate_client_secrets = MagicMock(
                return_value={"value": "new-secret-abc"}
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/credentials"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["client_id"] == "acme-partner-acme-001"
            assert data["client_secret"] == "new-secret-abc"
            assert data["grant_type"] == "client_credentials"
            assert "token" in data["token_endpoint"]

    def test_get_credentials_no_keycloak_client_404(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test 404 when consumer has no Keycloak client configured."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": None}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "active"
        mock_consumer.status.value = "active"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "active"

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/credentials"
                )

            assert response.status_code == 404
            assert "No Keycloak client" in response.json()["detail"]

    def test_get_credentials_suspended_consumer_400(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test 400 when consumer is not active."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": "acme-partner", "status": "suspended"}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/credentials"
                )

            assert response.status_code == 400
            assert "must be active" in response.json()["detail"]

    def test_get_credentials_keycloak_unavailable_503(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test 503 with Retry-After when Keycloak is unreachable."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "keycloak_client_id": "acme-partner-acme-001"}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "active"
        mock_consumer.status.value = "active"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "active"

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus, \
             patch("src.routers.consumers.keycloak_service") as mock_kc:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_kc.get_client = AsyncMock(
                side_effect=RuntimeError("Keycloak not connected")
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/credentials"
                )

            assert response.status_code == 503
            assert response.headers.get("retry-after") == "5"

    def test_get_credentials_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session, sample_consumer_data
    ):
        """Test tenant isolation for credentials endpoint."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get(
                f"/v1/consumers/acme/{sample_consumer_data['id']}/credentials"
            )

        assert response.status_code == 403

    def test_get_credentials_consumer_not_found_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test 404 when consumer does not exist."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{uuid4()}/credentials"
                )

            assert response.status_code == 404
