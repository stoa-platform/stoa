"""
Tests for Plans Router - CAB-1121

Target: Plan CRUD + tenant isolation
Tests: 10 test cases
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestPlansRouter:
    """Test suite for Plans Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_plan(self, data: dict) -> MagicMock:
        """Create a mock Plan object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== Create Plan Tests ==============

    def test_create_plan_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test successful plan creation returns 201."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_slug = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(return_value=mock_plan)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/plans/acme",
                    json={
                        "slug": "gold",
                        "name": "Gold Plan",
                        "description": "High-volume plan",
                        "rate_limit_per_second": 100,
                        "rate_limit_per_minute": 5000,
                        "requires_approval": True,
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["slug"] == "gold"
            assert data["name"] == "Gold Plan"
            assert data["tenant_id"] == "acme"
            assert data["requires_approval"] is True

    def test_create_plan_duplicate_slug_409(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test duplicate slug returns 409."""
        mock_existing = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_slug = AsyncMock(return_value=mock_existing)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/plans/acme",
                    json={
                        "slug": "gold",
                        "name": "Duplicate Gold",
                    },
                )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_create_plan_invalid_slug_422(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test invalid slug format returns 422."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/plans/acme",
                json={
                    "slug": "Gold Plan!",  # Invalid: uppercase + special chars
                    "name": "Gold Plan",
                },
            )

        assert response.status_code == 422

    # ============== List Plans Tests ==============

    def test_list_plans_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test listing plans with pagination."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_plan], 1)
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/plans/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["slug"] == "gold"

    # ============== Get Plan Tests ==============

    def test_get_plan_by_id_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test getting a plan by UUID."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_plan)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/plans/acme/{sample_plan_data['id']}"
                )

            assert response.status_code == 200
            assert response.json()["slug"] == "gold"

    def test_get_plan_by_slug_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test getting a plan by slug."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_slug = AsyncMock(return_value=mock_plan)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/plans/acme/by-slug/gold")

            assert response.status_code == 200
            assert response.json()["name"] == "Gold Plan"

    def test_get_plan_404(self, app_with_tenant_admin, mock_db_session):
        """Test 404 when plan not found."""
        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/plans/acme/{uuid4()}")

            assert response.status_code == 404

    # ============== Update Plan Tests ==============

    def test_update_plan_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test updating a plan."""
        mock_plan = self._create_mock_plan(sample_plan_data)
        updated_plan = self._create_mock_plan(
            {**sample_plan_data, "name": "Gold Plan V2"}
        )

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_plan)
            mock_repo_instance.update = AsyncMock(return_value=updated_plan)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(
                    f"/v1/plans/acme/{sample_plan_data['id']}",
                    json={"name": "Gold Plan V2"},
                )

            assert response.status_code == 200
            assert response.json()["name"] == "Gold Plan V2"

    # ============== Delete Plan Tests ==============

    def test_delete_plan_success(
        self, app_with_tenant_admin, mock_db_session, sample_plan_data
    ):
        """Test deleting a plan."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_plan)
            mock_repo_instance.delete = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(
                    f"/v1/plans/acme/{sample_plan_data['id']}"
                )

            assert response.status_code == 204

    # ============== Authorization Tests ==============

    def test_plan_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session
    ):
        """Test tenant isolation - cannot access plans in another tenant."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/plans/acme")

        assert response.status_code == 403

    def test_cpi_admin_cross_tenant_access(
        self, app_with_cpi_admin, mock_db_session, sample_plan_data
    ):
        """Test CPI admin can access any tenant's plans."""
        mock_plan = self._create_mock_plan(sample_plan_data)

        with patch("src.routers.plans.PlanRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(
                return_value=([mock_plan], 1)
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/plans/acme")

            assert response.status_code == 200
            assert response.json()["total"] == 1
