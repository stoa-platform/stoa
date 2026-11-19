"""Regression: creating a subscription must not log the subscriber's e-mail.

CodeQL py/clear-text-logging-sensitive-data (alert 1522) flagged the
"Created subscription" line, which interpolated user.email into the log.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.models.portal_application import SecurityProfile
from tests.test_regression_cab_1967_apikey_subscription import (
    EMIT_APPROVED_PATH,
    EMIT_CREATED_PATH,
    PLAN_REPO_PATH,
    PORTAL_APP_REPO_PATH,
    PROVISION_PATH,
    SUB_REPO_PATH,
    _mock_subscription,
)


def test_regression_created_subscription_log_has_no_email(app_with_tenant_admin, mock_db_session, caplog):
    sub = _mock_subscription()
    sub_repo = MagicMock()
    sub_repo.get_by_application_and_api = AsyncMock(return_value=None)
    sub_repo.create = AsyncMock(return_value=sub)
    sub_repo.update_status = AsyncMock(return_value=sub)
    plan = MagicMock(requires_approval=False)
    plan_repo = MagicMock(get_by_id=AsyncMock(return_value=plan))
    portal_app = MagicMock(keycloak_client_id=None, security_profile=SecurityProfile.API_KEY)
    portal_app_repo = MagicMock(get_by_id=AsyncMock(return_value=portal_app))

    with (
        caplog.at_level(logging.INFO),
        patch(SUB_REPO_PATH, return_value=sub_repo),
        patch(PLAN_REPO_PATH, return_value=plan_repo),
        patch(PORTAL_APP_REPO_PATH, return_value=portal_app_repo),
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

    assert resp.status_code == 201
    created = [r.getMessage() for r in caplog.records if "Created subscription" in r.getMessage()]
    assert created, "the creation log line is still expected"
    assert all("admin@acme.com" not in line for line in created)
    assert all("tenant-admin-user-id" in line for line in created)
