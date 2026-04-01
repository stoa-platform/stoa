"""Regression test for CAB-1938: API uniqueness on (tenant_id, api_name, version) with slug api_id.

Ticket: CAB-1938
Root cause: Old unique constraint was on (tenant_id, api_id) without version awareness.
  Two APIs with the same name but different versions would conflict. Soft-deleted APIs
  blocked re-creation of the same name.
Invariant:
  - Same (name, version) in same tenant → 409
  - Same name, different version → OK
  - api_id is auto-generated slug from name
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.models.catalog import APICatalog

CATALOG_REPO_PATH = "src.routers.apis.CatalogRepository"
KAFKA_PATH = "src.routers.apis.kafka_service"


def _mock_catalog_api(**overrides) -> APICatalog:
    """Build a mock APICatalog row for CAB-1938 tests."""
    defaults = {
        "api_id": "weather-api",
        "tenant_id": "acme",
        "api_name": "Weather API",
        "version": "1.0.0",
        "status": "draft",
        "tags": [],
        "portal_published": False,
        "api_metadata": {
            "name": "Weather API",
            "display_name": "Weather API",
            "version": "1.0.0",
            "description": "Weather data",
            "backend_url": "https://api.weather.com",
            "status": "draft",
            "deployments": {"dev": False, "staging": False},
        },
        "openapi_spec": None,
        "deleted_at": None,
    }
    defaults.update(overrides)
    mock = MagicMock(spec=APICatalog)
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


class TestSlugify:
    """Unit tests for _slugify helper."""

    def test_simple_name(self):
        from src.routers.apis import _slugify

        assert _slugify("My Cool API") == "my-cool-api"

    def test_special_characters(self):
        from src.routers.apis import _slugify

        assert _slugify("API@v2.0 (beta)") == "apiv20-beta"

    def test_multiple_spaces_and_hyphens(self):
        from src.routers.apis import _slugify

        assert _slugify("my  --  api") == "my-api"

    def test_leading_trailing_whitespace(self):
        from src.routers.apis import _slugify

        assert _slugify("  hello world  ") == "hello-world"

    def test_empty_string_fallback(self):
        from src.routers.apis import _slugify

        assert _slugify("!!!") == "api"

    def test_already_slug(self):
        from src.routers.apis import _slugify

        assert _slugify("my-api") == "my-api"

    def test_uppercase(self):
        from src.routers.apis import _slugify

        assert _slugify("Payment Gateway") == "payment-gateway"

    def test_numbers_preserved(self):
        from src.routers.apis import _slugify

        assert _slugify("API v3") == "api-v3"

    def test_unicode_stripped(self):
        from src.routers.apis import _slugify

        assert _slugify("café-api") == "caf-api"

    def test_single_char(self):
        from src.routers.apis import _slugify

        assert _slugify("x") == "x"


class TestApiFromCatalogDisplayName:
    """Ensure _api_from_catalog reads display_name from metadata."""

    def test_display_name_from_metadata(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(
            api_metadata={
                "display_name": "My Pretty API",
                "description": "desc",
                "backend_url": "http://backend",
                "deployments": {},
            }
        )
        result = _api_from_catalog(api)
        assert result.display_name == "My Pretty API"

    def test_display_name_fallback_to_api_name(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(api_metadata={"description": "", "backend_url": "", "deployments": {}})
        result = _api_from_catalog(api)
        assert result.display_name == "Weather API"

    def test_display_name_fallback_to_api_id(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(
            api_name=None,
            api_metadata={"description": "", "backend_url": "", "deployments": {}},
        )
        result = _api_from_catalog(api)
        assert result.display_name == "weather-api"


class TestCreateApiSlugGeneration:
    """Verify create_api generates slug from name (CAB-1938 core behavior)."""

    def test_create_generates_slug_from_name(self, app_with_tenant_admin, client_as_tenant_admin):
        """Name with spaces → slug in response id and name fields."""
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "My Weather API",
                    "display_name": "My Weather API",
                    "backend_url": "https://api.weather.com",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "my-weather-api"
        assert body["id"] == "my-weather-api"
        assert body["display_name"] == "My Weather API"

    def test_create_special_chars_in_name(self, app_with_tenant_admin, client_as_tenant_admin):
        """Special characters stripped, result is clean slug."""
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "API@v2.0 (beta)",
                    "display_name": "API v2.0 Beta",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "apiv20-beta"

    def test_create_preserves_version(self, app_with_tenant_admin, client_as_tenant_admin):
        """Version from request body is used, not the default."""
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "versioned-api",
                    "display_name": "Versioned API",
                    "version": "2.1.0",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["version"] == "2.1.0"

    def test_create_default_version(self, app_with_tenant_admin, client_as_tenant_admin):
        """Omitting version defaults to 1.0.0."""
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "no-version-api",
                    "display_name": "No Version",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["version"] == "1.0.0"


class TestCreateApiDuplicate409:
    """Verify 409 on duplicate (name, version) with correct error message (CAB-1938)."""

    def test_duplicate_returns_409_with_name_version_message(self, app_with_tenant_admin, client_as_tenant_admin):
        """409 error detail includes API name and version."""
        from src.database import get_db

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # tenant lookup
                Exception("duplicate key violates unique constraint"),
            ]
        )
        mock_session.rollback = AsyncMock()
        mock_session.commit = AsyncMock()

        async def _override_db():
            yield mock_session

        app_with_tenant_admin.dependency_overrides[get_db] = _override_db

        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH):
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "Payment API",
                    "display_name": "Payment API",
                    "version": "2.0.0",
                    "backend_url": "https://pay.example.com",
                },
            )

        app_with_tenant_admin.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "Payment API" in detail
        assert "2.0.0" in detail


class TestUpdateApiNoChanges:
    """Verify update with empty body returns current state without DB write."""

    def test_update_empty_body_returns_current(self, app_with_tenant_admin, client_as_tenant_admin):
        mock_api = _mock_catalog_api()
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=mock_api)
            with patch(KAFKA_PATH):
                resp = client_as_tenant_admin.put(
                    "/v1/tenants/acme/apis/weather-api",
                    json={},
                )

        assert resp.status_code == 200
        assert resp.json()["name"] == "weather-api"


class TestDeleteApiSoftDelete:
    """Verify delete sets deleted_at (soft delete, not hard delete)."""

    def test_delete_sets_deleted_at(self, app_with_tenant_admin, client_as_tenant_admin):
        mock_api = _mock_catalog_api()
        mock_api.deleted_at = None

        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=mock_api)
            with patch(KAFKA_PATH) as mock_kafka:
                mock_kafka.emit_api_deleted = AsyncMock(return_value="evt-1")
                mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
                resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/weather-api")

        assert resp.status_code == 200
        assert mock_api.deleted_at is not None


class TestListApiVersionsEmpty:
    """Verify versions endpoint returns empty list (GitLab migration pending)."""

    def test_versions_returns_empty(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=_mock_catalog_api())
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/weather-api/versions")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_versions_404_for_missing_api(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/missing/versions")

        assert resp.status_code == 404
