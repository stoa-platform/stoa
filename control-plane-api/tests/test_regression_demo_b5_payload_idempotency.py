"""Regression tests for demo smoke payload/idempotency path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String

from src.models.subscription import Subscription
from src.routers import applications as applications_router
from tests.test_applications_router import API_KEY_SVC_PATH, KC_SVC_PATH, SUB_REPO_PATH


def test_regression_demo_b5_subscription_provisioning_status_matches_migration() -> None:
    assert isinstance(Subscription.__table__.c.provisioning_status.type, String)


def test_regression_demo_b5_subscription_api_key_prefix_fits_generated_prefix() -> None:
    assert Subscription.__table__.c.api_key_prefix.type.length >= 12


def test_regression_demo_b5_create_application_demo_mode_skips_keycloak(
    app_with_tenant_admin, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(applications_router.settings, "STOA_DISABLE_AUTH", True)

    with (
        patch(f"{KC_SVC_PATH}.create_client", new=AsyncMock()) as create_client,
        TestClient(app_with_tenant_admin) as client,
    ):
        resp = client.post(
            "/v1/tenants/acme/applications",
            headers={"X-Demo-Mode": "true"},
            json={"name": "demo-app-smoke", "display_name": "demo-app-smoke"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "demo-acme-demo-app-smoke"
    assert data["name"] == "demo-app-smoke"
    assert data["display_name"] == "demo-app-smoke"
    create_client.assert_not_awaited()


def test_regression_demo_b5_subscribe_demo_application_returns_key_without_keycloak(
    app_with_tenant_admin, mock_db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(applications_router.settings, "STOA_DISABLE_AUTH", True)

    subscription = MagicMock()
    subscription.id = "sub-demo"
    subscription.status.value = "active"

    mock_sub_repo = MagicMock()
    mock_sub_repo.create = AsyncMock(return_value=subscription)

    with (
        patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock()) as get_client_by_id,
        patch(API_KEY_SVC_PATH) as mock_api_key_svc,
        patch(SUB_REPO_PATH, return_value=mock_sub_repo),
        TestClient(app_with_tenant_admin) as client,
    ):
        mock_api_key_svc.generate_key.return_value = ("stoa_sk_demo", "demo-hash", "stoa_sk_demo")
        resp = client.post(
            "/v1/tenants/acme/applications/demo-acme-demo-app-smoke/subscribe/demo-api-smoke",
            headers={"X-Demo-Mode": "true"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == "stoa_sk_demo"
    assert data["api_key_prefix"] == "stoa_sk_demo"
    assert data["status"] == "active"
    get_client_by_id.assert_not_awaited()
    mock_sub_repo.create.assert_awaited_once()
    mock_db_session.commit.assert_awaited_once()
