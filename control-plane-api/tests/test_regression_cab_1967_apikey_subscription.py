"""Regression test for CAB-1967: subscription endpoint rejects api_key apps.

PR: #1879
Ticket: CAB-1967
Root cause: POST /v1/subscriptions unconditionally required keycloak_client_id,
  which api_key profile apps don't have. The check now skips OAuth2 validation
  when the app's security_profile is 'api_key'.
Invariant: api_key apps can subscribe without a Keycloak client; OAuth2 apps still require one.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.models.portal_application import SecurityProfile
from src.models.subscription import SubscriptionStatus

SUB_REPO_PATH = "src.routers.subscriptions.SubscriptionRepository"
PLAN_REPO_PATH = "src.routers.subscriptions.PlanRepository"
PORTAL_APP_REPO_PATH = "src.routers.subscriptions.PortalApplicationRepository"
EMIT_CREATED_PATH = "src.routers.subscriptions.emit_subscription_created"
EMIT_APPROVED_PATH = "src.routers.subscriptions.emit_subscription_approved"
PROVISION_PATH = "src.routers.subscriptions.provision_on_approval"


def _mock_subscription(**overrides):
    from datetime import datetime
    from uuid import uuid4

    mock = MagicMock()
    sid = uuid4()
    defaults = {
        "id": sid,
        "application_id": "00000000-0000-4000-8000-000000000001",
        "application_name": "API Key App",
        "subscriber_id": "tenant-admin-user-id",
        "subscriber_email": "admin@acme.com",
        "api_id": "api-1",
        "api_name": "Test API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "plan_id": str(uuid4()),
        "plan_name": "Basic",
        "api_key_hash": None,
        "api_key_prefix": None,
        "oauth_client_id": None,
        "status": SubscriptionStatus.ACTIVE,
        "status_reason": None,
        "expires_at": None,
        "previous_key_expires_at": None,
        "previous_api_key_hash": None,
        "last_rotated_at": None,
        "rotation_count": 0,
        "ttl_extension_count": 0,
        "ttl_total_extended_days": 0,
        "approved_at": None,
        "revoked_at": None,
        "approved_by": None,
        "revoked_by": None,
        "rejected_by": None,
        "rejected_at": None,
        "provisioning_status": "none",
        "gateway_app_id": None,
        "provisioning_error": None,
        "provisioned_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def test_regression_cab_1967_apikey_app_can_subscribe(app_with_tenant_admin, mock_db_session):
    """api_key profile apps must be able to subscribe without keycloak_client_id."""
    sub = _mock_subscription()
    mock_sub_repo = MagicMock()
    mock_sub_repo.get_by_application_and_api = AsyncMock(return_value=None)
    mock_sub_repo.create = AsyncMock(return_value=sub)
    mock_sub_repo.update_status = AsyncMock(return_value=sub)

    mock_plan_repo = MagicMock()
    mock_plan = MagicMock()
    mock_plan.requires_approval = False
    mock_plan_repo.get_by_id = AsyncMock(return_value=mock_plan)

    # api_key app: no keycloak_client_id, security_profile=API_KEY
    mock_portal_app = MagicMock()
    mock_portal_app.keycloak_client_id = None
    mock_portal_app.security_profile = SecurityProfile.API_KEY
    mock_portal_app_repo = MagicMock()
    mock_portal_app_repo.get_by_id = AsyncMock(return_value=mock_portal_app)

    with (
        patch(SUB_REPO_PATH, return_value=mock_sub_repo),
        patch(PLAN_REPO_PATH, return_value=mock_plan_repo),
        patch(PORTAL_APP_REPO_PATH, return_value=mock_portal_app_repo),
        patch(EMIT_CREATED_PATH, new=AsyncMock()),
        patch(EMIT_APPROVED_PATH, new=AsyncMock()),
        patch(PROVISION_PATH, new=AsyncMock()),
        TestClient(app_with_tenant_admin) as client,
    ):
        resp = client.post(
            "/v1/subscriptions",
            json={
                "application_id": "00000000-0000-4000-8000-000000000001",
                "application_name": "API Key App",
                "api_id": "api-1",
                "api_name": "Test API",
                "api_version": "1.0",
                "tenant_id": "acme",
            },
        )

    # Before fix: 400 "Application has no OAuth2 client configured."
    assert resp.status_code == 201
    data = resp.json()
    assert data["oauth_client_id"] is None


def test_regression_cab_1967_oauth2_app_still_requires_kc_client(app_with_tenant_admin, mock_db_session):
    """OAuth2 apps without keycloak_client_id must still be rejected."""
    mock_sub_repo = MagicMock()
    mock_sub_repo.get_by_application_and_api = AsyncMock(return_value=None)

    # OAuth2 app with no keycloak_client_id
    mock_portal_app = MagicMock()
    mock_portal_app.keycloak_client_id = None
    mock_portal_app.security_profile = SecurityProfile.OAUTH2_PUBLIC
    mock_portal_app_repo = MagicMock()
    mock_portal_app_repo.get_by_id = AsyncMock(return_value=mock_portal_app)

    with (
        patch(SUB_REPO_PATH, return_value=mock_sub_repo),
        patch(PORTAL_APP_REPO_PATH, return_value=mock_portal_app_repo),
        TestClient(app_with_tenant_admin) as client,
    ):
        resp = client.post(
            "/v1/subscriptions",
            json={
                "application_id": "00000000-0000-4000-8000-000000000001",
                "application_name": "OAuth App",
                "api_id": "api-1",
                "api_name": "Test API",
                "api_version": "1.0",
                "tenant_id": "acme",
            },
        )

    assert resp.status_code == 400
    assert "OAuth2 client configured" in resp.json()["detail"]
