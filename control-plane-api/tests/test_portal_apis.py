"""
Tests for Portal APIs endpoint (CAB-1044: Search edge cases).

Tests the /v1/portal/apis endpoint, specifically search functionality
with special characters that could cause SQL LIKE injection issues.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestPortalAPIsSearch:
    """Test search functionality edge cases for Portal APIs endpoint."""

    @pytest.fixture
    def mock_catalog_repo(self):
        """Mock CatalogRepository to return empty results."""
        with patch('src.routers.portal.CatalogRepository') as mock_class:
            mock_repo = MagicMock()
            mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))
            mock_class.return_value = mock_repo
            yield mock_repo

    def test_search_apis_normal(self, client_as_tenant_admin, mock_catalog_repo):
        """Normal search term works correctly."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=oasis")
        assert response.status_code == 200
        data = response.json()
        assert "apis" in data
        assert "total" in data

    def test_search_apis_empty_string(self, client_as_tenant_admin, mock_catalog_repo):
        """Empty search string returns all APIs (no filter applied)."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=")
        assert response.status_code == 200
        data = response.json()
        assert "apis" in data

    def test_search_apis_whitespace_only(self, client_as_tenant_admin, mock_catalog_repo):
        """Whitespace-only search returns all APIs (no filter applied)."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=   ")
        assert response.status_code == 200
        data = response.json()
        assert "apis" in data

    def test_search_apis_percent_char(self, client_as_tenant_admin, mock_catalog_repo):
        """Percent character (LIKE wildcard) is properly escaped."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=%25")  # URL encoded %
        assert response.status_code == 200, "Search with % should not cause 500 error"

    def test_search_apis_underscore_char(self, client_as_tenant_admin, mock_catalog_repo):
        """Underscore character (LIKE single-char wildcard) is properly escaped."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=_")
        assert response.status_code == 200, "Search with _ should not cause 500 error"

    def test_search_apis_backslash_char(self, client_as_tenant_admin, mock_catalog_repo):
        """Backslash character (LIKE escape char) is properly escaped."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=%5C")  # URL encoded \
        assert response.status_code == 200, "Search with \\ should not cause 500 error"

    def test_search_apis_single_quote(self, client_as_tenant_admin, mock_catalog_repo):
        """Single quote character is handled safely."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search='")
        assert response.status_code == 200, "Search with ' should not cause 500 error"

    def test_search_apis_double_quote(self, client_as_tenant_admin, mock_catalog_repo):
        """Double quote character is handled safely."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=%22")  # URL encoded "
        assert response.status_code == 200, "Search with \" should not cause 500 error"

    def test_search_apis_semicolon(self, client_as_tenant_admin, mock_catalog_repo):
        """Semicolon character is handled safely."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=;")
        assert response.status_code == 200, "Search with ; should not cause 500 error"

    def test_search_apis_sql_injection_attempt(self, client_as_tenant_admin, mock_catalog_repo):
        """SQL injection attempts are safely escaped."""
        # Classic SQL injection patterns
        injection_attempts = [
            "'; DROP TABLE api_catalog; --",
            "1 OR 1=1",
            "' OR ''='",
            "admin'--",
        ]
        for attempt in injection_attempts:
            response = client_as_tenant_admin.get(f"/v1/portal/apis?search={attempt}")
            assert response.status_code == 200, f"SQL injection attempt should not cause error: {attempt}"

    def test_search_apis_special_chars_combined(self, client_as_tenant_admin, mock_catalog_repo):
        """Multiple special characters combined are handled safely."""
        response = client_as_tenant_admin.get("/v1/portal/apis?search=%25_%5C")  # %_\
        assert response.status_code == 200, "Combined special chars should not cause 500 error"


class TestEscapeLikeFunction:
    """Unit tests for the escape_like helper function."""

    def test_escape_percent(self):
        """Percent sign is escaped."""
        from src.repositories.catalog import escape_like
        assert escape_like("test%value") == "test\\%value"

    def test_escape_underscore(self):
        """Underscore is escaped."""
        from src.repositories.catalog import escape_like
        assert escape_like("test_value") == "test\\_value"

    def test_escape_backslash(self):
        """Backslash is escaped."""
        from src.repositories.catalog import escape_like
        assert escape_like("test\\value") == "test\\\\value"

    def test_escape_all_special(self):
        """All special characters are escaped in order."""
        from src.repositories.catalog import escape_like
        # Order matters: backslash must be escaped first
        assert escape_like("%_\\") == "\\%\\_\\\\"

    def test_escape_normal_string(self):
        """Normal string without special chars is unchanged."""
        from src.repositories.catalog import escape_like
        assert escape_like("normalstring") == "normalstring"

    def test_escape_empty_string(self):
        """Empty string returns empty string."""
        from src.repositories.catalog import escape_like
        assert escape_like("") == ""


class TestPortalAPIsSortBy:
    """Tests for sort_by parameter on /v1/portal/apis (CAB-1906)."""

    @pytest.fixture
    def mock_catalog_repo(self):
        with patch('src.routers.portal.CatalogRepository') as mock_class:
            mock_repo = MagicMock()
            mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))
            mock_class.return_value = mock_repo
            yield mock_repo

    def test_sort_by_name(self, client_as_tenant_admin, mock_catalog_repo):
        """sort_by=name is accepted and passed to repository."""
        response = client_as_tenant_admin.get("/v1/portal/apis?sort_by=name")
        assert response.status_code == 200
        mock_catalog_repo.get_portal_apis.assert_called_once()
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["sort_by"] == "name"

    def test_sort_by_updated_at(self, client_as_tenant_admin, mock_catalog_repo):
        """sort_by=updated_at is accepted."""
        response = client_as_tenant_admin.get("/v1/portal/apis?sort_by=updated_at")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["sort_by"] == "updated_at"

    def test_sort_by_created_at(self, client_as_tenant_admin, mock_catalog_repo):
        """sort_by=created_at is accepted."""
        response = client_as_tenant_admin.get("/v1/portal/apis?sort_by=created_at")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["sort_by"] == "created_at"

    def test_sort_by_default_none(self, client_as_tenant_admin, mock_catalog_repo):
        """sort_by defaults to None when not provided."""
        response = client_as_tenant_admin.get("/v1/portal/apis")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["sort_by"] is None


class TestPortalAPIsAuthType:
    """Tests for auth_type filter parameter on /v1/portal/apis (CAB-1906)."""

    @pytest.fixture
    def mock_catalog_repo(self):
        with patch('src.routers.portal.CatalogRepository') as mock_class:
            mock_repo = MagicMock()
            mock_repo.get_portal_apis = AsyncMock(return_value=([], 0))
            mock_class.return_value = mock_repo
            yield mock_repo

    def test_auth_type_oauth2(self, client_as_tenant_admin, mock_catalog_repo):
        """auth_type=oauth2 is accepted and passed to repository."""
        response = client_as_tenant_admin.get("/v1/portal/apis?auth_type=oauth2")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["auth_type"] == "oauth2"

    def test_auth_type_api_key(self, client_as_tenant_admin, mock_catalog_repo):
        """auth_type=api_key is accepted."""
        response = client_as_tenant_admin.get("/v1/portal/apis?auth_type=api_key")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["auth_type"] == "api_key"

    def test_auth_type_default_none(self, client_as_tenant_admin, mock_catalog_repo):
        """auth_type defaults to None when not provided."""
        response = client_as_tenant_admin.get("/v1/portal/apis")
        assert response.status_code == 200
        call_kwargs = mock_catalog_repo.get_portal_apis.call_args[1]
        assert call_kwargs["auth_type"] is None


class TestInferAuthType:
    """Tests for _infer_auth_type helper (CAB-1906)."""

    def test_oauth2(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["rest", "oauth2"]) == "OAuth2"

    def test_oidc(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["oidc", "payments"]) == "OAuth2"

    def test_api_key(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["api-key", "rest"]) == "API Key"

    def test_mtls(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["mtls"]) == "mTLS"

    def test_basic(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["basic-auth"]) == "Basic"

    def test_none(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type(["rest", "graphql"]) is None

    def test_empty(self):
        from src.routers.portal import _infer_auth_type
        assert _infer_auth_type([]) is None


class TestCountEndpoints:
    """Tests for _count_endpoints helper (CAB-1906)."""

    def test_counts_methods(self):
        from src.routers.portal import _count_endpoints
        spec = {"paths": {"/users": {"get": {}, "post": {}}, "/users/{id}": {"get": {}, "delete": {}}}}
        assert _count_endpoints(spec) == 4

    def test_empty_paths(self):
        from src.routers.portal import _count_endpoints
        assert _count_endpoints({"paths": {}}) == 0

    def test_none_spec(self):
        from src.routers.portal import _count_endpoints
        assert _count_endpoints(None) == 0

    def test_ignores_non_methods(self):
        from src.routers.portal import _count_endpoints
        spec = {"paths": {"/users": {"get": {}, "parameters": []}}}
        assert _count_endpoints(spec) == 1
