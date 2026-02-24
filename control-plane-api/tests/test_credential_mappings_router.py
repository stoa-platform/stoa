"""Tests for Credential Mappings Router — CAB-1448

Covers: /v1/tenants/{tenant_id}/credential-mappings
        CRUD + sync + RBAC (cpi-admin, tenant-admin, viewer, cross-tenant).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

REPO_PATH = "src.routers.credential_mappings.CredentialMappingRepository"
TENANT_ID = "acme"


def _make_mapping(**overrides):
    """Create a mock CredentialMapping model."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "consumer_id": uuid4(),
        "api_id": "weather-api",
        "tenant_id": TENANT_ID,
        "auth_type": MagicMock(value="api_key"),
        "header_name": "X-Api-Key",
        "encrypted_value": b"encrypted-secret",
        "description": "Test mapping",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "admin-user-id",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestCreateCredentialMapping:
    """Tests for POST /v1/tenants/{tenant_id}/credential-mappings."""

    def test_create_success(self, client_as_tenant_admin):
        mapping = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.get_by_consumer_and_api = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=mapping)

        with (
            patch(REPO_PATH) as MockRepo,
            patch(
                "src.routers.credential_mappings.CredentialMappingRepository.encrypt_credential",
                return_value=b"encrypted",
            ),
        ):
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/credential-mappings",
                json={
                    "consumer_id": str(mapping.consumer_id),
                    "api_id": "weather-api",
                    "auth_type": "api_key",
                    "header_name": "X-Api-Key",
                    "credential_value": "secret-123",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["api_id"] == "weather-api"
        assert data["has_credential"] is True

    def test_create_duplicate_409(self, client_as_tenant_admin):
        existing = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.get_by_consumer_and_api = AsyncMock(return_value=existing)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/credential-mappings",
                json={
                    "consumer_id": str(existing.consumer_id),
                    "api_id": "weather-api",
                    "auth_type": "api_key",
                    "header_name": "X-Api-Key",
                    "credential_value": "secret-123",
                },
            )

        assert resp.status_code == 409

    def test_create_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.post(
            f"/v1/tenants/{TENANT_ID}/credential-mappings",
            json={
                "consumer_id": str(uuid4()),
                "api_id": "weather-api",
                "auth_type": "api_key",
                "header_name": "X-Api-Key",
                "credential_value": "secret-123",
            },
        )
        assert resp.status_code == 403

    def test_create_403_viewer(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.post(
            f"/v1/tenants/{TENANT_ID}/credential-mappings",
            json={
                "consumer_id": str(uuid4()),
                "api_id": "weather-api",
                "auth_type": "api_key",
                "header_name": "X-Api-Key",
                "credential_value": "secret-123",
            },
        )
        assert resp.status_code == 403


class TestListCredentialMappings:
    """Tests for GET /v1/tenants/{tenant_id}/credential-mappings."""

    def test_list_success(self, client_as_tenant_admin):
        mapping = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([mapping], 1))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_empty(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_403_other_tenant(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/tenants/{TENANT_ID}/credential-mappings")
        assert resp.status_code == 403


class TestGetCredentialMapping:
    """Tests for GET /v1/tenants/{tenant_id}/credential-mappings/{mapping_id}."""

    def test_get_success(self, client_as_tenant_admin):
        mapping = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mapping)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings/{mapping.id}")

        assert resp.status_code == 200

    def test_get_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings/{uuid4()}")

        assert resp.status_code == 404

    def test_get_wrong_tenant_404(self, client_as_tenant_admin):
        mapping = _make_mapping(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mapping)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings/{mapping.id}")

        assert resp.status_code == 404


class TestUpdateCredentialMapping:
    """Tests for PUT /v1/tenants/{tenant_id}/credential-mappings/{mapping_id}."""

    def test_update_success(self, client_as_tenant_admin):
        mapping = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_repo.update = AsyncMock(return_value=mapping)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.put(
                f"/v1/tenants/{TENANT_ID}/credential-mappings/{mapping.id}",
                json={"description": "Updated desc"},
            )

        assert resp.status_code == 200

    def test_update_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.put(
                f"/v1/tenants/{TENANT_ID}/credential-mappings/{uuid4()}",
                json={"description": "test"},
            )

        assert resp.status_code == 404


class TestDeleteCredentialMapping:
    """Tests for DELETE /v1/tenants/{tenant_id}/credential-mappings/{mapping_id}."""

    def test_delete_success(self, client_as_tenant_admin):
        mapping = _make_mapping()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_repo.update = AsyncMock(return_value=mapping)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.delete(f"/v1/tenants/{TENANT_ID}/credential-mappings/{mapping.id}")

        assert resp.status_code == 204

    def test_delete_404(self, client_as_tenant_admin):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_tenant_admin.delete(f"/v1/tenants/{TENANT_ID}/credential-mappings/{uuid4()}")

        assert resp.status_code == 404


class TestSyncCredentialMappings:
    """Tests for GET /v1/tenants/{tenant_id}/credential-mappings/sync/{gateway_id}."""

    def test_sync_success_cpi_admin(self, client_as_cpi_admin):
        mock_repo = MagicMock()
        mock_repo.list_active_for_sync = AsyncMock(
            return_value=[
                {
                    "consumer_id": str(uuid4()),
                    "api_id": "weather-api",
                    "auth_type": "api_key",
                    "header_name": "X-Api-Key",
                    "header_value": "decrypted-secret",
                }
            ]
        )

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value = mock_repo
            resp = client_as_cpi_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings/sync/gw-instance-1")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_sync_403_tenant_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/credential-mappings/sync/gw-instance-1")
        assert resp.status_code == 403
