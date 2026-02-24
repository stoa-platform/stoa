"""Tests for Federation Router — CAB-1436

Covers: /v1/tenants/{tenant_id}/federation/accounts
- Master account CRUD (create, list, get, update, delete)
- Sub-account CRUD (create, list, get, update, revoke)
- Delegation token, usage, bulk revoke
- Tool allow-list (set, get)
- RBAC (cpi-admin, tenant-admin, viewer, cross-tenant)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

SVC_PATH = "src.routers.federation.FederationService"
BASE = "/v1/tenants/acme/federation/accounts"

MASTER_ID = uuid4()
SUB_ID = uuid4()


def _mock_master(**overrides):
    """Create a mock MasterAccount."""
    mock = MagicMock()
    defaults = {
        "id": MASTER_ID,
        "tenant_id": "acme",
        "name": "acme-federation",
        "display_name": "ACME Federation",
        "description": "Main federation account",
        "status": "active",
        "max_sub_accounts": 10,
        "quota_config": {"monthly_requests": 100000},
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "admin-user-id",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_sub(**overrides):
    """Create a mock SubAccount."""
    mock = MagicMock()
    defaults = {
        "id": SUB_ID,
        "master_account_id": MASTER_ID,
        "tenant_id": "acme",
        "name": "agent-alpha",
        "display_name": "Agent Alpha",
        "account_type": "agent",
        "status": "active",
        "api_key_prefix": "stoa_sk_agt",
        "api_key_hash": "hashed",
        "kc_client_id": "kc-client-1",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "admin-user-id",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestCreateMasterAccount:
    """Tests for POST /v1/tenants/{tenant_id}/federation/accounts."""

    def test_create_success(self, app_with_cpi_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.create_master_account = AsyncMock(return_value=master)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                BASE,
                json={
                    "name": "acme-federation",
                    "display_name": "ACME Federation",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "acme-federation"

    def test_create_conflict(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.create_master_account = AsyncMock(side_effect=ValueError("duplicate name"))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post(BASE, json={"name": "dup"})

        assert resp.status_code == 409

    def test_create_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post(BASE, json={"name": "test"})

        assert resp.status_code == 403


class TestListMasterAccounts:
    """Tests for GET /v1/tenants/{tenant_id}/federation/accounts."""

    def test_list_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.list_master_accounts = AsyncMock(return_value=([master], 1))
        mock_svc.count_sub_accounts = AsyncMock(return_value=2)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(BASE)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["sub_account_count"] == 2

    def test_list_with_status_filter(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_master_accounts = AsyncMock(return_value=([], 0))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}?status=active")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_403_cross_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(BASE)

        assert resp.status_code == 403


class TestGetMasterAccount:
    """Tests for GET /v1/tenants/{tenant_id}/federation/accounts/{account_id}."""

    def test_get_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.count_sub_accounts = AsyncMock(return_value=3)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{MASTER_ID}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "acme-federation"

    def test_get_404(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{uuid4()}")

        assert resp.status_code == 404


class TestUpdateMasterAccount:
    """Tests for PATCH /v1/tenants/{tenant_id}/federation/accounts/{account_id}."""

    def test_update_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        updated = _mock_master(display_name="Updated Name")
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.update_master_account = AsyncMock(return_value=updated)
        mock_svc.count_sub_accounts = AsyncMock(return_value=0)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(f"{BASE}/{MASTER_ID}", json={"display_name": "Updated Name"})

        assert resp.status_code == 200

    def test_update_404(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(f"{BASE}/{uuid4()}", json={"display_name": "X"})

        assert resp.status_code == 404


class TestDeleteMasterAccount:
    """Tests for DELETE /v1/tenants/{tenant_id}/federation/accounts/{account_id}."""

    def test_delete_success(self, app_with_cpi_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.delete_master_account = AsyncMock()

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"{BASE}/{MASTER_ID}")

        assert resp.status_code == 204

    def test_delete_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Only cpi-admin can delete master accounts."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"{BASE}/{MASTER_ID}")

        assert resp.status_code == 403

    def test_delete_404(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"{BASE}/{uuid4()}")

        assert resp.status_code == 404


class TestCreateSubAccount:
    """Tests for POST .../accounts/{id}/sub-accounts."""

    def test_create_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        sub = _mock_sub()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.create_sub_account = AsyncMock(return_value=(sub, "stoa_sk_plaintext_key"))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"{BASE}/{MASTER_ID}/sub-accounts",
                json={
                    "name": "agent-alpha",
                    "display_name": "Agent Alpha",
                    "account_type": "agent",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["api_key"] == "stoa_sk_plaintext_key"

    def test_create_master_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"{BASE}/{uuid4()}/sub-accounts",
                json={
                    "name": "test",
                    "account_type": "developer",
                },
            )

        assert resp.status_code == 404

    def test_create_conflict(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.create_sub_account = AsyncMock(side_effect=ValueError("limit reached"))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"{BASE}/{MASTER_ID}/sub-accounts",
                json={
                    "name": "x",
                    "account_type": "developer",
                },
            )

        assert resp.status_code == 409


class TestListSubAccounts:
    """Tests for GET .../accounts/{id}/sub-accounts."""

    def test_list_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        sub = _mock_sub()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.list_sub_accounts = AsyncMock(return_value=([sub], 1))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{MASTER_ID}/sub-accounts")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_master_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{uuid4()}/sub-accounts")

        assert resp.status_code == 404


class TestRevokeSubAccount:
    """Tests for POST .../sub-accounts/{sub_id}/revoke."""

    def test_revoke_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_sub(status="revoked")
        mock_svc = MagicMock()
        mock_svc.get_sub_account = AsyncMock(return_value=_mock_sub())
        mock_svc.revoke_sub_account = AsyncMock(return_value=sub)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"{BASE}/{MASTER_ID}/sub-accounts/{SUB_ID}/revoke")

        assert resp.status_code == 200

    def test_revoke_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_sub_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"{BASE}/{MASTER_ID}/sub-accounts/{uuid4()}/revoke")

        assert resp.status_code == 404


class TestDelegateToken:
    """Tests for POST .../accounts/{id}/delegate-token."""

    def test_delegate_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        sub = _mock_sub()
        token_data = {
            "access_token": "tok-123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "stoa:read",
        }
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.get_sub_account = AsyncMock(return_value=sub)
        mock_svc.delegate_token = AsyncMock(return_value=token_data)

        url = f"{BASE}/{MASTER_ID}/delegate-token?sub_account_id={SUB_ID}"
        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(url, json={"scopes": ["stoa:read"], "ttl_seconds": 3600})

        assert resp.status_code == 200
        assert resp.json()["access_token"] == "tok-123"

    def test_delegate_master_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"{BASE}/{uuid4()}/delegate-token",
                json={"scopes": ["stoa:read"], "ttl_seconds": 3600},
            )

        assert resp.status_code == 404


class TestGetUsage:
    """Tests for GET .../accounts/{id}/usage."""

    def test_usage_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.get_usage_aggregation = AsyncMock(
            return_value=[
                {
                    "sub_account_id": str(SUB_ID),
                    "sub_account_name": "partner-a",
                    "request_count": 100,
                    "token_count": 5000,
                },
            ]
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{MASTER_ID}/usage")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 100

    def test_usage_master_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"{BASE}/{uuid4()}/usage")

        assert resp.status_code == 404


class TestBulkRevoke:
    """Tests for POST .../accounts/{id}/bulk-revoke."""

    def test_bulk_revoke_success(self, app_with_tenant_admin, mock_db_session):
        master = _mock_master()
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=master)
        mock_svc.bulk_revoke = AsyncMock(return_value=(3, 1, 4))

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"{BASE}/{MASTER_ID}/bulk-revoke")

        assert resp.status_code == 200
        data = resp.json()
        assert data["revoked_count"] == 3
        assert data["already_revoked"] == 1

    def test_bulk_revoke_master_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_master_account = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"{BASE}/{uuid4()}/bulk-revoke")

        assert resp.status_code == 404


class TestToolAllowList:
    """Tests for PUT/GET .../sub-accounts/{sub_id}/tools."""

    def test_set_tools_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_sub()
        mock_svc = MagicMock()
        mock_svc.get_sub_account = AsyncMock(return_value=sub)
        mock_svc.set_tool_allow_list = AsyncMock(return_value=["tool-1", "tool-2"])

        url = f"{BASE}/{MASTER_ID}/sub-accounts/{SUB_ID}/tools"
        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.put(url, json={"tools": ["tool-1", "tool-2"]})

        assert resp.status_code == 200
        assert resp.json()["tools"] == ["tool-1", "tool-2"]

    def test_get_tools_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_sub()
        mock_svc = MagicMock()
        mock_svc.get_sub_account = AsyncMock(return_value=sub)
        mock_svc.get_tool_allow_list = AsyncMock(return_value=["tool-1"])

        url = f"{BASE}/{MASTER_ID}/sub-accounts/{SUB_ID}/tools"
        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(url)

        assert resp.status_code == 200
        assert resp.json()["tools"] == ["tool-1"]

    def test_set_tools_sub_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_sub_account = AsyncMock(return_value=None)

        url = f"{BASE}/{MASTER_ID}/sub-accounts/{uuid4()}/tools"
        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.put(url, json={"tools": ["tool-1"]})

        assert resp.status_code == 404
