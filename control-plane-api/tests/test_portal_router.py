"""Tests for Portal Router — CAB-1436

Covers: /v1/portal (apis, apis/{id}, apis/{id}/openapi, mcp-servers,
        api-categories, api-universes, api-tags, mcp-categories)
       /v1/internal/catalog/apis
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

CATALOG_REPO = "src.routers.portal.CatalogRepository"


def _make_cached_api(**overrides):
    """Create a mock CatalogAPI (CachedPortalAPI row)."""
    mock = MagicMock()
    defaults = {
        "api_id": "acme/weather-api",
        "api_name": "weather-api",
        "tenant_id": "acme",
        "version": "1.0.0",
        "status": "published",
        "category": "platform",
        "tags": ["rest", "weather"],
        "portal_published": True,
        "audience": "public",
        "api_metadata": {
            "display_name": "Weather API",
            "description": "Get weather data",
            "backend_url": "https://api.weather.com",
            "deployments": {},
        },
        "openapi_spec": {"openapi": "3.0.0", "info": {"title": "Weather API", "version": "1.0.0"}, "paths": {}},
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestListPortalAPIs:
    """Tests for GET /v1/portal/apis."""

    def test_list_apis_success(self, app_with_tenant_admin, mock_db_session):
        """List portal APIs with default params."""
        api = _make_cached_api()
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=([api], 1))

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["apis"]) == 1
        assert data["apis"][0]["name"] == "weather-api"

    def test_list_apis_with_search(self, app_with_tenant_admin, mock_db_session):
        """List APIs with search filter."""
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis?search=weather&page=1&page_size=10")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_apis_with_universe_filter(self, app_with_tenant_admin, mock_db_session):
        """List APIs filtered by universe."""
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis?universe=oasis")

        assert resp.status_code == 200

    def test_list_apis_empty(self, app_with_tenant_admin, mock_db_session):
        """List APIs returns empty when none exist."""
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis")

        assert resp.status_code == 200
        assert resp.json()["apis"] == []


class TestGetPortalAPI:
    """Tests for GET /v1/portal/apis/{api_id}."""

    def test_get_api_by_name_only(self, app_with_tenant_admin, mock_db_session):
        """Get API by name (cross-tenant search)."""
        api = _make_cached_api()
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=api)

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/weather-api")

        assert resp.status_code == 200

    def test_get_api_404(self, app_with_tenant_admin, mock_db_session):
        """Non-existent API returns 404."""
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=None)

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/nonexistent")

        assert resp.status_code == 404

    def test_get_api_audience_denied(self, app_with_tenant_admin, mock_db_session):
        """API with restricted audience returns 404 for unauthorized role."""
        api = _make_cached_api(audience="internal")
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=api)

        with (
            patch(CATALOG_REPO, return_value=mock_repo),
            patch(
                "src.routers.portal.get_allowed_audiences",
                return_value=["public"],
            ),
        ):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/internal-api")

        assert resp.status_code == 404


class TestGetPortalAPIOpenAPI:
    """Tests for GET /v1/portal/apis/{api_id}/openapi."""

    def test_get_openapi_success(self, app_with_tenant_admin, mock_db_session):
        """Get OpenAPI spec for an API."""
        api = _make_cached_api()
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=api)

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/weather-api/openapi")

        assert resp.status_code == 200
        data = resp.json()
        assert data["openapi"] == "3.0.0"

    def test_get_openapi_no_spec(self, app_with_tenant_admin, mock_db_session):
        """Get OpenAPI returns minimal spec when not available."""
        api = _make_cached_api(openapi_spec=None)
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=api)

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/weather-api/openapi")

        assert resp.status_code == 200
        data = resp.json()
        assert data["openapi"] == "3.0.0"
        assert data["paths"] == {}

    def test_get_openapi_404(self, app_with_tenant_admin, mock_db_session):
        """Non-existent API OpenAPI returns 404."""
        mock_repo = MagicMock()
        mock_repo.find_api_by_name = AsyncMock(return_value=None)

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/apis/nonexistent/openapi")

        assert resp.status_code == 404


class TestPortalCategories:
    """Tests for GET /v1/portal/api-categories."""

    def test_get_categories_from_db(self, app_with_tenant_admin, mock_db_session):
        """Get categories from database."""
        mock_repo = MagicMock()
        mock_repo.get_categories = AsyncMock(return_value=["platform", "ai", "data"])

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/api-categories")

        assert resp.status_code == 200
        data = resp.json()
        assert "ai" in data
        assert "data" in data
        assert "platform" in data

    def test_get_categories_defaults_when_empty(self, app_with_tenant_admin, mock_db_session):
        """Get categories returns defaults when database is empty."""
        mock_repo = MagicMock()
        mock_repo.get_categories = AsyncMock(return_value=[])

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/api-categories")

        assert resp.status_code == 200
        data = resp.json()
        assert "platform" in data
        assert "ai" in data


class TestPortalUniverses:
    """Tests for GET /v1/portal/api-universes."""

    def test_get_universes(self, app_with_tenant_admin, mock_db_session):
        """Get available API universes."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/portal/api-universes")

        assert resp.status_code == 200
        data = resp.json()
        ids = [u["id"] for u in data]
        assert "oasis" in ids
        assert "enterprise" in ids


class TestPortalTags:
    """Tests for GET /v1/portal/api-tags."""

    def test_get_tags_from_db(self, app_with_tenant_admin, mock_db_session):
        """Get tags from database."""
        mock_repo = MagicMock()
        mock_repo.get_tags = AsyncMock(return_value=["rest", "graphql", "internal"])

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/api-tags")

        assert resp.status_code == 200
        data = resp.json()
        assert "graphql" in data
        assert "rest" in data

    def test_get_tags_defaults_when_empty(self, app_with_tenant_admin, mock_db_session):
        """Get tags returns defaults when database is empty."""
        mock_repo = MagicMock()
        mock_repo.get_tags = AsyncMock(return_value=[])

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/portal/api-tags")

        assert resp.status_code == 200
        data = resp.json()
        assert "rest" in data


class TestMCPCategories:
    """Tests for GET /v1/portal/mcp-categories."""

    def test_get_mcp_categories(self, app_with_tenant_admin, mock_db_session):
        """Get MCP server categories."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/portal/mcp-categories")

        assert resp.status_code == 200
        data = resp.json()
        assert "platform" in data
        assert "tenant" in data
        assert "public" in data


class TestInternalCatalogAPIs:
    """Tests for GET /v1/internal/catalog/apis (no auth)."""

    def test_internal_list_apis(self, app, mock_db_session):
        """Internal endpoint lists APIs without auth."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        api = _make_cached_api()
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=([api], 1))

        with patch(CATALOG_REPO, return_value=mock_repo):
            with TestClient(app) as client:
                resp = client.get("/v1/internal/catalog/apis")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["apis"]) == 1
        assert data["apis"][0]["name"] == "weather-api"

        app.dependency_overrides.clear()
