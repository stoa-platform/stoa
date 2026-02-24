"""Tests for Plans Router — CAB-1448

Covers: /v1/plans (CRUD — create, list, get by id, get by slug, update, delete).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

REPO_PATH = "src.routers.plans.PlanRepository"
TENANT_ID = "acme"


def _make_plan(**overrides):
    """Create a mock Plan model."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "slug": "gold",
        "name": "Gold Plan",
        "description": "High-volume plan",
        "tenant_id": TENANT_ID,
        "rate_limit_per_second": 100,
        "rate_limit_per_minute": 5000,
        "daily_request_limit": 1000000,
        "monthly_request_limit": 30000000,
        "burst_limit": 200,
        "requires_approval": True,
        "auto_approve_roles": None,
        "status": "active",
        "pricing_metadata": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "admin-user-id",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestCreatePlan:
    """Tests for POST /v1/plans/{tenant_id}."""

    def test_create_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_slug = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(
                f"/v1/plans/{TENANT_ID}",
                json={
                    "slug": "gold",
                    "name": "Gold Plan",
                    "rate_limit_per_second": 100,
                    "rate_limit_per_minute": 5000,
                    "daily_request_limit": 1000000,
                    "monthly_request_limit": 30000000,
                },
            )

        assert resp.status_code == 201

    def test_create_duplicate_409(self, client_as_tenant_admin):
        existing = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_slug = AsyncMock(return_value=existing)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(
                f"/v1/plans/{TENANT_ID}",
                json={
                    "slug": "gold",
                    "name": "Gold Plan",
                    "rate_limit_per_second": 100,
                    "rate_limit_per_minute": 5000,
                    "daily_request_limit": 1000000,
                    "monthly_request_limit": 30000000,
                },
            )

        assert resp.status_code == 409

    def test_create_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.post(
            f"/v1/plans/{TENANT_ID}",
            json={
                "slug": "gold",
                "name": "Gold Plan",
                "rate_limit_per_second": 100,
                "rate_limit_per_minute": 5000,
                "daily_request_limit": 1000000,
                "monthly_request_limit": 30000000,
            },
        )
        assert resp.status_code == 403


class TestListPlans:
    """Tests for GET /v1/plans/{tenant_id}."""

    def test_list_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([plan], 1))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_empty(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/plans/{TENANT_ID}")
        assert resp.status_code == 403


class TestGetPlanBySlug:
    """Tests for GET /v1/plans/{tenant_id}/by-slug/{slug}."""

    def test_get_by_slug_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_slug = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}/by-slug/gold")

        assert resp.status_code == 200

    def test_get_by_slug_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_slug = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}/by-slug/nonexistent")

        assert resp.status_code == 404


class TestGetPlanById:
    """Tests for GET /v1/plans/{tenant_id}/{plan_id}."""

    def test_get_by_id_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}/{plan.id}")

        assert resp.status_code == 200

    def test_get_by_id_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}/{uuid4()}")

        assert resp.status_code == 404

    def test_get_by_id_wrong_tenant(self, client_as_tenant_admin):
        plan = _make_plan(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/plans/{TENANT_ID}/{plan.id}")

        assert resp.status_code == 404


class TestUpdatePlan:
    """Tests for PUT /v1/plans/{tenant_id}/{plan_id}."""

    def test_update_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=plan)
        mock_repo.update = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.put(
                f"/v1/plans/{TENANT_ID}/{plan.id}",
                json={"name": "Updated Gold Plan"},
            )

        assert resp.status_code == 200

    def test_update_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.put(
                f"/v1/plans/{TENANT_ID}/{uuid4()}",
                json={"name": "test"},
            )

        assert resp.status_code == 404


class TestDeletePlan:
    """Tests for DELETE /v1/plans/{tenant_id}/{plan_id}."""

    def test_delete_success(self, client_as_tenant_admin):
        plan = _make_plan()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=plan)
        mock_repo.delete = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.delete(f"/v1/plans/{TENANT_ID}/{plan.id}")

        assert resp.status_code == 204

    def test_delete_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.delete(f"/v1/plans/{TENANT_ID}/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_wrong_tenant(self, client_as_tenant_admin):
        plan = _make_plan(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=plan)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.delete(f"/v1/plans/{TENANT_ID}/{plan.id}")

        assert resp.status_code == 404
