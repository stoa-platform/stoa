"""Tests for Backend APIs Router — CAB-1378

Endpoints:
- POST /v1/tenants/{tenant_id}/backend-apis (201)
- GET /v1/tenants/{tenant_id}/backend-apis
- GET /v1/tenants/{tenant_id}/backend-apis/{api_id}
- PATCH /v1/tenants/{tenant_id}/backend-apis/{api_id}
- DELETE /v1/tenants/{tenant_id}/backend-apis/{api_id} (204)
- POST /v1/tenants/{tenant_id}/saas-keys (201)
- GET /v1/tenants/{tenant_id}/saas-keys
- GET /v1/tenants/{tenant_id}/saas-keys/{key_id}
- DELETE /v1/tenants/{tenant_id}/saas-keys/{key_id} (204)

Auth: get_current_user + inline tenant check.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

REPO_PATH = "src.routers.backend_apis.BackendApiRepository"
KEY_REPO_PATH = "src.routers.backend_apis.SaasApiKeyRepository"
ENCRYPT_PATH = "src.routers.backend_apis.encrypt_auth_config"

BASE = "/v1/tenants/acme/backend-apis"
KEYS_BASE = "/v1/tenants/acme/saas-keys"


def _mock_backend_api(**overrides):
    """Create a mock BackendApi matching _to_response fields."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "name": "payment-api",
        "display_name": "Payment API",
        "description": "Process payments",
        "backend_url": "https://api.payments.com",
        "openapi_spec_url": None,
        "auth_type": "bearer",
        "auth_config_encrypted": None,
        "status": "draft",
        "tool_count": 0,
        "spec_hash": None,
        "last_synced_at": None,
        "created_at": datetime(2026, 2, 1),
        "updated_at": datetime(2026, 2, 1),
        "created_by": "admin-user-id",
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


def _mock_saas_key(**overrides):
    """Create a mock SaasApiKey matching SaasApiKeyResponse schema."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "name": "test-key",
        "description": "Test API key",
        "key_prefix": "stoa_saas_ab12",
        "key_hash": "abcdef1234567890",
        "allowed_backend_api_ids": [],
        "rate_limit_rpm": 60,
        "status": "active",
        "expires_at": None,
        "revoked_at": None,
        "last_used_at": None,
        "created_by": "admin-user-id",
        "created_at": datetime(2026, 2, 1),
        "updated_at": datetime(2026, 2, 1),
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


class TestBackendApis:
    """Tests for Backend API CRUD endpoints."""

    def test_create_backend_api_success(self, app_with_tenant_admin, mock_db_session):
        """POST / creates a new backend API (201)."""
        mock_api = _mock_backend_api()

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_tenant_and_name = AsyncMock(return_value=None)
            MockRepo.return_value.create = AsyncMock(return_value=mock_api)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "payment-api",
                        "display_name": "Payment API",
                        "backend_url": "https://api.payments.com",
                        "auth_type": "bearer",
                    },
                )

        assert response.status_code == 201
        mock_db_session.commit.assert_awaited()

    def test_create_backend_api_409_duplicate(self, app_with_tenant_admin, mock_db_session):
        """POST / returns 409 when name already exists."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_tenant_and_name = AsyncMock(
                return_value=_mock_backend_api()
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "name": "payment-api",
                        "display_name": "Payment API",
                        "backend_url": "https://api.payments.com",
                        "auth_type": "bearer",
                    },
                )

        assert response.status_code == 409

    def test_list_backend_apis_success(self, app_with_tenant_admin, mock_db_session):
        """GET / returns paginated list."""
        items = [_mock_backend_api()]

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_by_tenant = AsyncMock(return_value=(items, 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_get_backend_api_success(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} returns API details."""
        api_id = uuid4()
        mock_api = _mock_backend_api(id=api_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_api)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}/{api_id}")

        assert response.status_code == 200

    def test_get_backend_api_404(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} returns 404 when not found."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}/{uuid4()}")

        assert response.status_code == 404

    def test_update_backend_api_success(self, app_with_tenant_admin, mock_db_session):
        """PATCH /{id} updates API."""
        api_id = uuid4()
        mock_api = _mock_backend_api(id=api_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_api)
            MockRepo.return_value.update = AsyncMock(return_value=mock_api)

            with TestClient(app_with_tenant_admin) as client:
                response = client.patch(
                    f"{BASE}/{api_id}",
                    json={"display_name": "Updated Name"},
                )

        assert response.status_code == 200

    def test_delete_backend_api_success(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} deletes API (204)."""
        api_id = uuid4()
        mock_api = _mock_backend_api(id=api_id)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_api)
            MockRepo.return_value.delete = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{BASE}/{api_id}")

        assert response.status_code == 204

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        """GET / returns 403 for wrong tenant."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get(BASE)

        assert response.status_code == 403


class TestSaasApiKeys:
    """Tests for SaaS API Key endpoints."""

    def test_create_saas_key_success(self, app_with_tenant_admin, mock_db_session):
        """POST / creates a new API key (201)."""
        api_id = uuid4()
        mock_key = _mock_saas_key()
        mock_api = _mock_backend_api(id=api_id)

        with (
            patch(KEY_REPO_PATH) as MockKeyRepo,
            patch(REPO_PATH) as MockApiRepo,
        ):
            MockApiRepo.return_value.get_by_id = AsyncMock(return_value=mock_api)
            MockKeyRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))
            MockKeyRepo.return_value.create = AsyncMock(return_value=mock_key)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    KEYS_BASE,
                    json={
                        "name": "test-key",
                        "description": "Test key",
                        "allowed_backend_api_ids": [str(api_id)],
                    },
                )

        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        assert data["name"] == "test-key"

    def test_list_saas_keys_success(self, app_with_tenant_admin, mock_db_session):
        """GET / returns paginated key list."""
        items = [_mock_saas_key()]

        with patch(KEY_REPO_PATH) as MockKeyRepo:
            MockKeyRepo.return_value.list_by_tenant = AsyncMock(return_value=(items, 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(KEYS_BASE)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_get_saas_key_success(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} returns key details."""
        key_id = uuid4()
        mock_key = _mock_saas_key(id=key_id)

        with patch(KEY_REPO_PATH) as MockKeyRepo:
            MockKeyRepo.return_value.get_by_id = AsyncMock(return_value=mock_key)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{KEYS_BASE}/{key_id}")

        assert response.status_code == 200

    def test_revoke_saas_key_success(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} revokes key (204)."""
        key_id = uuid4()
        mock_key = _mock_saas_key(id=key_id)

        with patch(KEY_REPO_PATH) as MockKeyRepo:
            MockKeyRepo.return_value.get_by_id = AsyncMock(return_value=mock_key)
            MockKeyRepo.return_value.update = AsyncMock(return_value=mock_key)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{KEYS_BASE}/{key_id}")

        assert response.status_code == 204

    def test_revoke_saas_key_404(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} returns 404 when key not found."""
        with patch(KEY_REPO_PATH) as MockKeyRepo:
            MockKeyRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{KEYS_BASE}/{uuid4()}")

        assert response.status_code == 404
