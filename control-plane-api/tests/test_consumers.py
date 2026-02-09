"""
Tests for Consumers Router - CAB-1121

Target: Consumer CRUD + status management + tenant isolation
Tests: 12 test cases
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestConsumersRouter:
    """Test suite for Consumers Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_consumer(self, data: dict) -> MagicMock:
        """Create a mock Consumer object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== Create Consumer Tests ==============

    def test_create_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test successful consumer creation returns 201."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_external_id = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "ACME Corp",
                        "email": "api@acme.com",
                        "company": "ACME Corporation",
                        "description": "Strategic API partner",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["external_id"] == "partner-acme-001"
            assert data["name"] == "ACME Corp"
            assert data["tenant_id"] == "acme"
            assert data["status"] == "active"

    def test_create_consumer_duplicate_409(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test duplicate external_id returns 409."""
        mock_existing = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_external_id = AsyncMock(return_value=mock_existing)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/consumers/acme",
                    json={
                        "external_id": "partner-acme-001",
                        "name": "Duplicate",
                        "email": "dup@acme.com",
                    },
                )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_create_consumer_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session
    ):
        """Test tenant isolation - cannot create consumer in another tenant."""
        with TestClient(app_with_other_tenant) as client:
            response = client.post(
                "/v1/consumers/acme",
                json={
                    "external_id": "partner-001",
                    "name": "Test",
                    "email": "test@test.com",
                },
            )

        assert response.status_code == 403

    # ============== List Consumer Tests ==============

    def test_list_consumers_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test listing consumers with pagination."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_consumer], 1)
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["external_id"] == "partner-acme-001"

    def test_list_consumers_empty(self, app_with_tenant_admin, mock_db_session):
        """Test listing consumers when none exist."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 0
            assert response.json()["items"] == []

    # ============== Get Consumer Tests ==============

    def test_get_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test getting a consumer by ID."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}"
                )

            assert response.status_code == 200
            assert response.json()["name"] == "ACME Corp"

    def test_get_consumer_404(self, app_with_tenant_admin, mock_db_session):
        """Test 404 when consumer not found."""
        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/consumers/acme/{uuid4()}")

            assert response.status_code == 404

    # ============== Update Consumer Tests ==============

    def test_update_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test updating a consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        updated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "name": "ACME Updated"}
        )

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update = AsyncMock(return_value=updated_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}",
                    json={"name": "ACME Updated"},
                )

            assert response.status_code == 200
            assert response.json()["name"] == "ACME Updated"

    # ============== Delete Consumer Tests ==============

    def test_delete_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test deleting a consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.delete = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}"
                )

            assert response.status_code == 204

    # ============== Status Management Tests ==============

    def test_suspend_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test suspending an active consumer."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)
        mock_consumer.status = "active"
        # ConsumerStatus comparison — mock the enum value
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "active"
        mock_consumer.status.value = "active"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "active"

        suspended_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended"}
        )

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update_status = AsyncMock(return_value=suspended_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/suspend"
                )

            assert response.status_code == 200

    def test_activate_consumer_success(
        self, app_with_tenant_admin, mock_db_session, sample_consumer_data
    ):
        """Test reactivating a suspended consumer."""
        mock_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "suspended"}
        )
        mock_consumer.status = MagicMock()
        mock_consumer.status.__eq__ = lambda _self, other: str(other) == "suspended"
        mock_consumer.status.value = "suspended"
        mock_consumer.status.__ne__ = lambda _self, other: str(other) != "suspended"

        activated_consumer = self._create_mock_consumer(
            {**sample_consumer_data, "status": "active"}
        )

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo, \
             patch("src.routers.consumers.ConsumerStatus") as MockStatus:
            MockStatus.ACTIVE = "active"
            MockStatus.SUSPENDED = "suspended"
            MockStatus.BLOCKED = "blocked"

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_consumer)
            mock_repo_instance.update_status = AsyncMock(return_value=activated_consumer)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/consumers/acme/{sample_consumer_data['id']}/activate"
                )

            assert response.status_code == 200

    def test_cpi_admin_cross_tenant_access(
        self, app_with_cpi_admin, mock_db_session, sample_consumer_data
    ):
        """Test CPI admin can access any tenant's consumers."""
        mock_consumer = self._create_mock_consumer(sample_consumer_data)

        with patch("src.routers.consumers.ConsumerRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_consumer], 1)
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/consumers/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 1
