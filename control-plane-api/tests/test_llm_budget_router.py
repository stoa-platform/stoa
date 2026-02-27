"""Tests for LLM budget router (CAB-1558)."""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth import User, get_current_user
from src.database import get_db
from src.routers.llm_budget import router


def _make_user(roles: list[str] | None = None, tenant_id: str = "acme") -> User:
    return User(
        id="user-1",
        username="testuser",
        email="test@example.com",
        roles=roles or ["tenant-admin"],
        tenant_id=tenant_id,
    )


def _provider_response(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "provider_name": "openai",
        "display_name": "OpenAI",
        "default_model": "gpt-4",
        "cost_per_input_token": Decimal("0.00003"),
        "cost_per_output_token": Decimal("0.00006"),
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    # Provide dict() for Pydantic serialization
    m.dict.return_value = defaults
    m.model_dump.return_value = defaults
    return m


def _budget_response(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "monthly_limit_usd": Decimal("100.00"),
        "current_spend_usd": Decimal("25.00"),
        "alert_threshold_pct": 80,
        "usage_pct": 25.0,
        "remaining_usd": Decimal("75.00"),
        "is_over_budget": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    m.dict.return_value = defaults
    m.model_dump.return_value = defaults
    return m


def _spend_response(**overrides) -> MagicMock:
    defaults = {
        "tenant_id": "acme",
        "monthly_limit_usd": Decimal("100.00"),
        "current_spend_usd": Decimal("25.00"),
        "remaining_usd": Decimal("75.00"),
        "usage_pct": 25.0,
        "is_over_budget": False,
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    m.dict.return_value = defaults
    m.model_dump.return_value = defaults
    return m


@pytest.fixture
def app():
    """Create FastAPI app with router and mock dependencies."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def admin_client(app):
    """Client authenticated as cpi-admin."""
    user = _make_user(roles=["cpi-admin"], tenant_id="acme")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def tenant_client(app):
    """Client authenticated as tenant-admin for 'acme'."""
    user = _make_user(roles=["tenant-admin"], tenant_id="acme")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def other_tenant_client(app):
    """Client authenticated as tenant-admin for 'other-corp'."""
    user = _make_user(roles=["tenant-admin"], tenant_id="other-corp")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Access Control ──


class TestTenantAccess:
    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_admin_can_access_any_tenant(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.list_providers.return_value = []
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/any-tenant/llm/providers")

        assert resp.status_code == 200

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_tenant_admin_own_tenant(self, MockSvc, tenant_client):
        mock_svc = AsyncMock()
        mock_svc.list_providers.return_value = []
        MockSvc.return_value = mock_svc

        resp = tenant_client.get("/v1/tenants/acme/llm/providers")

        assert resp.status_code == 200

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_tenant_admin_other_tenant_forbidden(self, MockSvc, other_tenant_client):
        resp = other_tenant_client.get("/v1/tenants/acme/llm/providers")

        assert resp.status_code == 403


# ── Providers ──


class TestProviderEndpoints:
    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_create_provider_201(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.create_provider.return_value = _provider_response()
        MockSvc.return_value = mock_svc

        resp = admin_client.post(
            "/v1/tenants/acme/llm/providers",
            json={
                "provider_name": "openai",
                "display_name": "OpenAI",
                "default_model": "gpt-4",
                "cost_per_input_token": "0.00003",
                "cost_per_output_token": "0.00006",
                "status": "active",
            },
        )

        assert resp.status_code == 201

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_list_providers(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.list_providers.return_value = [_provider_response()]
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/acme/llm/providers")

        assert resp.status_code == 200

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_delete_provider_204(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.delete_provider.return_value = None
        MockSvc.return_value = mock_svc

        resp = admin_client.delete(f"/v1/tenants/acme/llm/providers/{uuid.uuid4()}")

        assert resp.status_code == 204

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_delete_provider_not_found_404(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.delete_provider.side_effect = ValueError("Provider not found")
        MockSvc.return_value = mock_svc

        resp = admin_client.delete(f"/v1/tenants/acme/llm/providers/{uuid.uuid4()}")

        assert resp.status_code == 404


# ── Budget ──


class TestBudgetEndpoints:
    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_create_budget_201(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.create_budget.return_value = _budget_response()
        MockSvc.return_value = mock_svc

        resp = admin_client.post(
            "/v1/tenants/acme/llm/budget",
            json={"monthly_limit_usd": "100.00"},
        )

        assert resp.status_code == 201

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_create_budget_conflict_409(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.create_budget.side_effect = ValueError("Budget already exists")
        MockSvc.return_value = mock_svc

        resp = admin_client.post(
            "/v1/tenants/acme/llm/budget",
            json={"monthly_limit_usd": "100.00"},
        )

        assert resp.status_code == 409

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_get_budget(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.get_budget.return_value = _budget_response()
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/acme/llm/budget")

        assert resp.status_code == 200

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_get_budget_not_found_404(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.get_budget.side_effect = ValueError("Budget not found")
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/acme/llm/budget")

        assert resp.status_code == 404

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_update_budget(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.update_budget.return_value = _budget_response()
        MockSvc.return_value = mock_svc

        resp = admin_client.put(
            "/v1/tenants/acme/llm/budget",
            json={"monthly_limit_usd": "200.00"},
        )

        assert resp.status_code == 200


# ── Spend ──


class TestSpendEndpoints:
    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_get_spend(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.get_spend_summary.return_value = _spend_response()
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/acme/llm/spend")

        assert resp.status_code == 200

    @patch("src.routers.llm_budget.LlmBudgetService")
    def test_get_spend_not_found_404(self, MockSvc, admin_client):
        mock_svc = AsyncMock()
        mock_svc.get_spend_summary.side_effect = ValueError("Budget not found")
        MockSvc.return_value = mock_svc

        resp = admin_client.get("/v1/tenants/acme/llm/spend")

        assert resp.status_code == 404
