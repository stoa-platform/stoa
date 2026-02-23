"""Tests for Credential Mapping — CAB-1432

Covers:
- Model + schema validation
- Repository CRUD + encryption round-trip
- Router endpoints (6 CRUD + sync)
- RBAC (tenant-admin, cpi-admin, viewer, cross-tenant isolation)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

REPO_PATH = "src.routers.credential_mappings.CredentialMappingRepository"
BASE = "/v1/tenants/acme/credential-mappings"

CONSUMER_ID = uuid4()
API_ID = "weather-api-v1"
MAPPING_ID = uuid4()


def _mock_mapping(**overrides):
    """Create a mock CredentialMapping matching _to_response fields."""
    mock = MagicMock()
    defaults = {
        "id": MAPPING_ID,
        "consumer_id": CONSUMER_ID,
        "api_id": API_ID,
        "tenant_id": "acme",
        "auth_type": MagicMock(value="api_key"),
        "header_name": "X-API-Key",
        "encrypted_value": "gAAAAABfake-encrypted-value",
        "description": "ACME weather key",
        "is_active": True,
        "created_at": datetime(2026, 2, 23, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 23, tzinfo=UTC),
        "created_by": "tenant-admin-user-id",
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


# ============== Schema Tests ==============


class TestCredentialMappingSchemas:
    """Tests for Pydantic schema validation."""

    def test_create_schema_valid(self):
        """CredentialMappingCreate accepts valid input."""
        from src.schemas.credential_mapping import CredentialMappingCreate

        schema = CredentialMappingCreate(
            consumer_id=CONSUMER_ID,
            api_id="weather-api-v1",
            auth_type="api_key",
            header_name="X-API-Key",
            credential_value="sk-live-abc123",
            description="Test key",
        )
        assert schema.consumer_id == CONSUMER_ID
        assert schema.auth_type == "api_key"

    def test_create_schema_rejects_empty_api_id(self):
        """CredentialMappingCreate rejects empty api_id."""
        from pydantic import ValidationError

        from src.schemas.credential_mapping import CredentialMappingCreate

        with pytest.raises(ValidationError):
            CredentialMappingCreate(
                consumer_id=CONSUMER_ID,
                api_id="",
                auth_type="api_key",
                header_name="X-API-Key",
                credential_value="sk-live-abc123",
            )

    def test_create_schema_rejects_empty_credential(self):
        """CredentialMappingCreate rejects empty credential_value."""
        from pydantic import ValidationError

        from src.schemas.credential_mapping import CredentialMappingCreate

        with pytest.raises(ValidationError):
            CredentialMappingCreate(
                consumer_id=CONSUMER_ID,
                api_id="weather-api",
                auth_type="bearer",
                header_name="Authorization",
                credential_value="",
            )

    def test_update_schema_partial(self):
        """CredentialMappingUpdate accepts partial updates."""
        from src.schemas.credential_mapping import CredentialMappingUpdate

        schema = CredentialMappingUpdate(is_active=False)
        assert schema.is_active is False
        assert schema.auth_type is None
        assert schema.credential_value is None

    def test_response_schema_from_attributes(self):
        """CredentialMappingResponse works with from_attributes."""
        from src.schemas.credential_mapping import CredentialMappingResponse

        resp = CredentialMappingResponse(
            id=MAPPING_ID,
            consumer_id=CONSUMER_ID,
            api_id=API_ID,
            tenant_id="acme",
            auth_type="api_key",
            header_name="X-API-Key",
            has_credential=True,
            description="Test",
            is_active=True,
            created_at=datetime(2026, 2, 23, tzinfo=UTC),
            updated_at=datetime(2026, 2, 23, tzinfo=UTC),
            created_by="admin",
        )
        assert resp.has_credential is True
        assert resp.auth_type == "api_key"

    def test_sync_item_schema(self):
        """CredentialMappingSyncItem carries decrypted value."""
        from src.schemas.credential_mapping import CredentialMappingSyncItem

        item = CredentialMappingSyncItem(
            consumer_id=str(CONSUMER_ID),
            api_id=API_ID,
            auth_type="api_key",
            header_name="X-API-Key",
            header_value="sk-live-abc123",
        )
        assert item.header_value == "sk-live-abc123"


# ============== Repository Tests ==============


class TestCredentialMappingRepository:
    """Tests for repository CRUD with mock DB session."""

    def test_encrypt_credential_round_trip(self):
        """Encrypt and decrypt credential value preserves plaintext."""
        from src.repositories.credential_mapping import CredentialMappingRepository
        from src.services.encryption_service import decrypt_auth_config

        encrypted = CredentialMappingRepository.encrypt_credential("sk-live-secret-123")
        decrypted = decrypt_auth_config(encrypted)
        assert decrypted["value"] == "sk-live-secret-123"

    @pytest.mark.asyncio
    async def test_create(self, mock_db_session):
        """Repository.create adds to session and refreshes."""
        from src.repositories.credential_mapping import CredentialMappingRepository

        repo = CredentialMappingRepository(mock_db_session)
        mapping = MagicMock()
        mock_db_session.refresh = AsyncMock()
        mock_db_session.flush = AsyncMock()

        result = await repo.create(mapping)

        mock_db_session.add.assert_called_once_with(mapping)
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(mapping)
        assert result is mapping

    @pytest.mark.asyncio
    async def test_get_by_id(self, mock_db_session):
        """Repository.get_by_id returns mapping or None."""
        from src.repositories.credential_mapping import CredentialMappingRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_mapping()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        repo = CredentialMappingRepository(mock_db_session)
        result = await repo.get_by_id(MAPPING_ID)

        assert result is not None
        assert result.id == MAPPING_ID

    @pytest.mark.asyncio
    async def test_get_by_consumer_and_api(self, mock_db_session):
        """Repository.get_by_consumer_and_api returns unique mapping."""
        from src.repositories.credential_mapping import CredentialMappingRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_mapping()
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        repo = CredentialMappingRepository(mock_db_session)
        result = await repo.get_by_consumer_and_api(CONSUMER_ID, API_ID)

        assert result is not None
        assert result.consumer_id == CONSUMER_ID

    @pytest.mark.asyncio
    async def test_delete(self, mock_db_session):
        """Repository.delete removes mapping from session."""
        from src.repositories.credential_mapping import CredentialMappingRepository

        repo = CredentialMappingRepository(mock_db_session)
        mapping = MagicMock()
        mock_db_session.delete = AsyncMock()
        mock_db_session.flush = AsyncMock()

        await repo.delete(mapping)

        mock_db_session.delete.assert_awaited_once_with(mapping)
        mock_db_session.flush.assert_awaited_once()


# ============== Router Tests ==============


class TestCredentialMappingRouter:
    """Tests for CRUD endpoints with mocked repository."""

    def test_create_201(self, app_with_tenant_admin, mock_db_session):
        """POST / creates a new credential mapping (201)."""
        mock_mapping = _mock_mapping()

        with (
            patch(REPO_PATH) as MockRepo,
            patch("src.routers.credential_mappings.CredentialMappingRepository.encrypt_credential") as mock_encrypt,
        ):
            MockRepo.return_value.get_by_consumer_and_api = AsyncMock(return_value=None)
            MockRepo.return_value.create = AsyncMock(return_value=mock_mapping)
            mock_encrypt.return_value = "encrypted-value"

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "consumer_id": str(CONSUMER_ID),
                        "api_id": API_ID,
                        "auth_type": "api_key",
                        "header_name": "X-API-Key",
                        "credential_value": "sk-live-abc123",
                        "description": "Test key",
                    },
                )

        assert response.status_code == 201
        data = response.json()
        assert data["api_id"] == API_ID
        assert data["has_credential"] is True
        assert "encrypted_value" not in data
        mock_db_session.commit.assert_awaited()

    def test_create_409_duplicate(self, app_with_tenant_admin, mock_db_session):
        """POST / returns 409 when consumer+api mapping already exists."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_consumer_and_api = AsyncMock(return_value=_mock_mapping())

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    BASE,
                    json={
                        "consumer_id": str(CONSUMER_ID),
                        "api_id": API_ID,
                        "auth_type": "api_key",
                        "header_name": "X-API-Key",
                        "credential_value": "sk-live-abc123",
                    },
                )

        assert response.status_code == 409

    def test_list_200(self, app_with_tenant_admin, mock_db_session):
        """GET / returns paginated list."""
        items = [_mock_mapping()]

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_by_tenant = AsyncMock(return_value=(items, 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["api_id"] == API_ID

    def test_list_with_filters(self, app_with_tenant_admin, mock_db_session):
        """GET /?consumer_id=...&api_id=... filters correctly."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}?consumer_id={CONSUMER_ID}&api_id={API_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_get_by_id_200(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} returns single mapping."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=_mock_mapping())

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}/{MAPPING_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["auth_type"] == "api_key"

    def test_get_by_id_404(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} returns 404 for missing mapping."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"{BASE}/{uuid4()}")

        assert response.status_code == 404

    def test_update_200(self, app_with_tenant_admin, mock_db_session):
        """PUT /{id} updates mapping."""
        updated_mapping = _mock_mapping(description="Updated description")

        with (
            patch(REPO_PATH) as MockRepo,
            patch("src.routers.credential_mappings.CredentialMappingRepository.encrypt_credential"),
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=_mock_mapping())
            MockRepo.return_value.update = AsyncMock(return_value=updated_mapping)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(
                    f"{BASE}/{MAPPING_ID}",
                    json={"description": "Updated description"},
                )

        assert response.status_code == 200
        mock_db_session.commit.assert_awaited()

    def test_update_404(self, app_with_tenant_admin, mock_db_session):
        """PUT /{id} returns 404 for missing mapping."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.put(
                    f"{BASE}/{uuid4()}",
                    json={"description": "Updated"},
                )

        assert response.status_code == 404

    def test_delete_204(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} soft-deletes (sets is_active=false) and returns 204."""
        mock_mapping = _mock_mapping()

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_mapping)
            MockRepo.return_value.update = AsyncMock(return_value=mock_mapping)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{BASE}/{MAPPING_ID}")

        assert response.status_code == 204
        assert mock_mapping.is_active is False
        mock_db_session.commit.assert_awaited()

    def test_delete_404(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} returns 404 for missing mapping."""
        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{BASE}/{uuid4()}")

        assert response.status_code == 404


# ============== Sync Endpoint Tests ==============


class TestCredentialMappingSync:
    """Tests for the admin sync endpoint."""

    def test_sync_200_admin(self, app_with_cpi_admin, mock_db_session):
        """GET /sync/{gw_id} returns decrypted mappings for admin."""
        sync_items = [
            {
                "consumer_id": str(CONSUMER_ID),
                "api_id": API_ID,
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "sk-live-abc123",
            }
        ]

        with patch(REPO_PATH) as MockRepo:
            MockRepo.return_value.list_active_for_sync = AsyncMock(return_value=sync_items)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}/sync/gw-instance-1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["header_value"] == "sk-live-abc123"

    def test_sync_403_non_admin(self, app_with_tenant_admin, mock_db_session):
        """GET /sync/{gw_id} returns 403 for non-admin user."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"{BASE}/sync/gw-instance-1")

        assert response.status_code == 403


# ============== RBAC Tests ==============


class TestCredentialMappingRBAC:
    """Tests for role-based access control."""

    def test_cross_tenant_isolation(self, app_with_other_tenant, mock_db_session):
        """User from different tenant cannot access mappings."""
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/tenants/acme/credential-mappings")

        assert response.status_code == 403

    def test_viewer_can_read(self, app, mock_db_session):
        """Viewer role can list credential mappings (read access)."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        async def override_user():
            return User(
                id="viewer-id",
                email="v@acme.com",
                username="viewer",
                roles=["viewer"],
                tenant_id="acme",
            )

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        try:
            with patch(REPO_PATH) as MockRepo:
                MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

                with TestClient(app) as client:
                    response = client.get(BASE)

            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_viewer_cannot_write(self, app, mock_db_session):
        """Viewer role cannot create credential mappings."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        async def override_user():
            return User(
                id="viewer-id",
                email="v@acme.com",
                username="viewer",
                roles=["viewer"],
                tenant_id="acme",
            )

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        try:
            with TestClient(app) as client:
                response = client.post(
                    BASE,
                    json={
                        "consumer_id": str(CONSUMER_ID),
                        "api_id": API_ID,
                        "auth_type": "api_key",
                        "header_name": "X-API-Key",
                        "credential_value": "sk-live-abc123",
                    },
                )

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
