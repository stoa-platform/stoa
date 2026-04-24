"""Regression tests for demo smoke API key handoff."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.test_applications_router import API_KEY_SVC_PATH, KC_SVC_PATH, SUB_REPO_PATH, _mock_kc_client


def test_regression_cab_demo_b1_subscribe_demo_mode_returns_one_time_api_key(
    app_with_tenant_admin, mock_db_session
):
    client_data = _mock_kc_client("app-1", "acme")
    subscription = MagicMock()
    subscription.id = "sub-1"
    subscription.status.value = "active"

    mock_sub_repo = MagicMock()
    mock_sub_repo.create = AsyncMock(return_value=subscription)

    with (
        patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
        patch(f"{KC_SVC_PATH}.update_client", new=AsyncMock(return_value=None)),
        patch(API_KEY_SVC_PATH) as mock_api_key_svc,
        patch(SUB_REPO_PATH, return_value=mock_sub_repo),
        TestClient(app_with_tenant_admin) as client,
    ):
        mock_api_key_svc.generate_key.return_value = ("stoa_sk_demo", "demo-hash", "stoa_sk_demo")
        resp = client.post(
            "/v1/tenants/acme/applications/app-1/subscribe/api-123",
            headers={"X-Demo-Mode": "true"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == "stoa_sk_demo"
    assert data["api_key_prefix"] == "stoa_sk_demo"
    assert data["status"] == "active"
    mock_sub_repo.create.assert_awaited_once()
    mock_db_session.commit.assert_awaited_once()
