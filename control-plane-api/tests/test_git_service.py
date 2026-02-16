"""Tests for GitLabService pure/sync helpers + mocked async methods (CAB-1291)"""
import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.git_service import (
    GITLAB_MAX_RETRIES,
    GITLAB_SEMAPHORE,
    GITLAB_TIMEOUT,
    GitLabRateLimitError,
    GitLabService,
    _fetch_with_protection,
    _normalize_api_data,
)


# ── Constants ──


class TestConstants:
    def test_semaphore_value(self):
        assert GITLAB_SEMAPHORE._value == 10

    def test_timeout(self):
        assert GITLAB_TIMEOUT == 5.0

    def test_max_retries(self):
        assert GITLAB_MAX_RETRIES == 3


# ── _normalize_api_data ──


class TestNormalizeApiData:
    def test_simple_format_passthrough(self):
        raw = {"id": "api-1", "name": "My API", "status": "active"}
        result = _normalize_api_data(raw)
        assert result is raw  # returned as-is

    def test_k8s_format(self):
        raw = {
            "apiVersion": "gostoa.dev/v1alpha1",
            "kind": "API",
            "metadata": {"name": "weather", "version": "2.0.0"},
            "spec": {
                "displayName": "Weather API",
                "description": "Forecast service",
                "backend": {"url": "http://backend:8080"},
                "status": "published",
                "deployments": {"dev": True, "staging": False},
            },
        }
        result = _normalize_api_data(raw)
        assert result["id"] == "weather"
        assert result["name"] == "weather"
        assert result["display_name"] == "Weather API"
        assert result["version"] == "2.0.0"
        assert result["description"] == "Forecast service"
        assert result["backend_url"] == "http://backend:8080"
        assert result["status"] == "published"
        assert result["deployments"]["dev"] is True
        assert result["deployments"]["staging"] is False

    def test_k8s_defaults(self):
        raw = {"apiVersion": "v1", "kind": "API", "metadata": {}, "spec": {}}
        result = _normalize_api_data(raw)
        assert result["id"] == ""
        assert result["version"] == "1.0.0"
        assert result["status"] == "draft"
        assert result["backend_url"] == ""
        assert result["deployments"]["dev"] is False

    def test_k8s_display_name_fallback(self):
        raw = {
            "apiVersion": "v1",
            "kind": "API",
            "metadata": {"name": "test-api"},
            "spec": {},
        }
        result = _normalize_api_data(raw)
        assert result["display_name"] == "test-api"


# ── Path helpers ──


class TestPathHelpers:
    def setup_method(self):
        self.svc = GitLabService()

    def test_get_tenant_path(self):
        assert self.svc._get_tenant_path("acme") == "tenants/acme"

    def test_get_api_path(self):
        assert self.svc._get_api_path("acme", "weather") == "tenants/acme/apis/weather"

    def test_get_mcp_server_path_platform(self):
        assert self.svc._get_mcp_server_path("_platform", "my-server") == "platform/mcp-servers/my-server"

    def test_get_mcp_server_path_tenant(self):
        assert self.svc._get_mcp_server_path("acme", "my-server") == "tenants/acme/mcp-servers/my-server"


# ── parse_tree_to_tenant_apis ──


class TestParseTreeToTenantApis:
    def setup_method(self):
        self.svc = GitLabService()

    def test_empty_tree(self):
        assert self.svc.parse_tree_to_tenant_apis([]) == {}

    def test_ignores_non_blobs(self):
        tree = [{"type": "tree", "path": "tenants/acme/apis/weather"}]
        assert self.svc.parse_tree_to_tenant_apis(tree) == {}

    def test_parses_api_yaml(self):
        tree = [
            {"type": "blob", "path": "tenants/acme/apis/weather/api.yaml"},
            {"type": "blob", "path": "tenants/acme/apis/weather/openapi.yaml"},
            {"type": "blob", "path": "tenants/corp/apis/billing/api.yaml"},
        ]
        result = self.svc.parse_tree_to_tenant_apis(tree)
        assert result == {"acme": ["weather"], "corp": ["billing"]}

    def test_multiple_apis_per_tenant(self):
        tree = [
            {"type": "blob", "path": "tenants/acme/apis/weather/api.yaml"},
            {"type": "blob", "path": "tenants/acme/apis/billing/api.yaml"},
        ]
        result = self.svc.parse_tree_to_tenant_apis(tree)
        assert set(result["acme"]) == {"weather", "billing"}

    def test_ignores_non_api_yaml(self):
        tree = [
            {"type": "blob", "path": "tenants/acme/apis/weather/openapi.yaml"},
            {"type": "blob", "path": "tenants/acme/tenant.yaml"},
        ]
        assert self.svc.parse_tree_to_tenant_apis(tree) == {}


# ── _normalize_mcp_server_data ──


class TestNormalizeMcpServerData:
    def setup_method(self):
        self.svc = GitLabService()

    def test_full_data(self):
        raw = {
            "metadata": {"name": "search-svc", "tenant": "acme", "version": "2.0.0"},
            "spec": {
                "displayName": "Search Service",
                "description": "Full-text search",
                "icon": "search-icon",
                "category": "tenant",
                "status": "active",
                "documentationUrl": "https://docs.example.com",
                "visibility": {"public": False, "roles": ["admin"], "excludeRoles": ["guest"]},
                "subscription": {
                    "requiresApproval": True,
                    "autoApproveRoles": ["admin"],
                    "defaultPlan": "pro",
                },
                "tools": [
                    {
                        "name": "search",
                        "displayName": "Search Tool",
                        "description": "Search docs",
                        "endpoint": "/search",
                        "method": "GET",
                        "enabled": True,
                        "requiresApproval": True,
                        "inputSchema": {"type": "object"},
                        "timeout": "60s",
                        "rateLimit": {"requestsPerMinute": 30},
                    }
                ],
                "backend": {
                    "baseUrl": "http://search:9200",
                    "auth": {"type": "bearer", "secretRef": "search-token"},
                    "timeout": "10s",
                    "retries": 5,
                },
            },
        }
        result = self.svc._normalize_mcp_server_data(raw, "tenants/acme/mcp-servers/search-svc")
        assert result["name"] == "search-svc"
        assert result["tenant_id"] == "acme"
        assert result["version"] == "2.0.0"
        assert result["display_name"] == "Search Service"
        assert result["description"] == "Full-text search"
        assert result["icon"] == "search-icon"
        assert result["category"] == "tenant"
        assert result["documentation_url"] == "https://docs.example.com"
        assert result["visibility"]["public"] is False
        assert result["visibility"]["roles"] == ["admin"]
        assert result["requires_approval"] is True
        assert result["auto_approve_roles"] == ["admin"]
        assert result["default_plan"] == "pro"
        assert result["git_path"] == "tenants/acme/mcp-servers/search-svc"
        # Tools
        assert len(result["tools"]) == 1
        tool = result["tools"][0]
        assert tool["name"] == "search"
        assert tool["display_name"] == "Search Tool"
        assert tool["method"] == "GET"
        assert tool["requires_approval"] is True
        assert tool["input_schema"] == {"type": "object"}
        assert tool["timeout"] == "60s"
        assert tool["rate_limit"] == 30
        # Backend
        assert result["backend"]["base_url"] == "http://search:9200"
        assert result["backend"]["auth_type"] == "bearer"
        assert result["backend"]["secret_ref"] == "search-token"
        assert result["backend"]["timeout"] == "10s"
        assert result["backend"]["retries"] == 5

    def test_minimal_data(self):
        raw = {"metadata": {}, "spec": {}}
        result = self.svc._normalize_mcp_server_data(raw, "path/to/server")
        assert result["name"] == ""
        assert result["tenant_id"] == "_platform"
        assert result["version"] == "1.0.0"
        assert result["category"] == "public"
        assert result["status"] == "active"
        assert result["tools"] == []
        assert result["backend"]["auth_type"] == "none"
        assert result["backend"]["retries"] == 3

    def test_tool_defaults(self):
        raw = {
            "metadata": {"name": "svc"},
            "spec": {"tools": [{"name": "tool-1"}]},
        }
        result = self.svc._normalize_mcp_server_data(raw, "path")
        tool = result["tools"][0]
        assert tool["display_name"] == "tool-1"  # fallback to name
        assert tool["method"] == "POST"
        assert tool["enabled"] is True
        assert tool["requires_approval"] is False
        assert tool["timeout"] == "30s"
        assert tool["rate_limit"] == 60


# ── Async methods (mocked GitLab) ──


class TestConnect:
    async def test_connect_success(self):
        svc = GitLabService()
        mock_gl = MagicMock()
        mock_project = MagicMock()
        mock_project.name = "stoa"
        mock_gl.projects.get.return_value = mock_project

        with patch("src.services.git_service.settings") as mock_settings:
            mock_settings.GITLAB_URL = "https://gitlab.example.com"
            mock_settings.GITLAB_TOKEN = "token"
            mock_settings.GITLAB_PROJECT_ID = 1
            with patch("src.services.git_service.gitlab.Gitlab", return_value=mock_gl):
                await svc.connect()

        assert svc._gl is mock_gl
        assert svc._project is mock_project
        mock_gl.auth.assert_called_once()

    async def test_connect_failure_raises(self):
        svc = GitLabService()
        with patch("src.services.git_service.settings") as mock_settings:
            mock_settings.GITLAB_URL = "https://gitlab.example.com"
            mock_settings.GITLAB_TOKEN = "token"
            mock_settings.GITLAB_PROJECT_ID = 1
            with patch("src.services.git_service.gitlab.Gitlab", side_effect=Exception("fail")):
                with pytest.raises(Exception, match="fail"):
                    await svc.connect()


class TestDisconnect:
    async def test_disconnect(self):
        svc = GitLabService()
        svc._gl = MagicMock()
        svc._project = MagicMock()
        await svc.disconnect()
        assert svc._gl is None
        assert svc._project is None


class TestGetTenant:
    async def test_not_connected(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_tenant("acme")

    async def test_found(self):
        svc = GitLabService()
        svc._project = MagicMock()
        mock_file = MagicMock()
        mock_file.decode.return_value = b"id: acme\nname: ACME Corp"
        svc._project.files.get.return_value = mock_file
        result = await svc.get_tenant("acme")
        assert result["id"] == "acme"

    async def test_not_found(self):
        import gitlab

        svc = GitLabService()
        svc._project = MagicMock()
        svc._project.files.get.side_effect = gitlab.exceptions.GitlabGetError(
            response_code=404, error_message="not found"
        )
        result = await svc.get_tenant("unknown")
        assert result is None


class TestGetApi:
    async def test_not_connected(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_api("acme", "weather")

    async def test_returns_normalized(self):
        svc = GitLabService()
        svc._project = MagicMock()
        mock_file = MagicMock()
        mock_file.decode.return_value = b"id: weather\nname: Weather API"
        svc._project.files.get.return_value = mock_file
        result = await svc.get_api("acme", "weather")
        assert result["id"] == "weather"

    async def test_not_found(self):
        import gitlab

        svc = GitLabService()
        svc._project = MagicMock()
        svc._project.files.get.side_effect = gitlab.exceptions.GitlabGetError(
            response_code=404, error_message="not found"
        )
        result = await svc.get_api("acme", "unknown")
        assert result is None

    async def test_yaml_error(self):
        svc = GitLabService()
        svc._project = MagicMock()
        mock_file = MagicMock()
        mock_file.decode.return_value = b": invalid yaml ]["
        svc._project.files.get.return_value = mock_file
        result = await svc.get_api("acme", "bad")
        assert result is None


class TestListApis:
    async def test_not_connected(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_apis("acme")

    async def test_empty(self):
        import gitlab

        svc = GitLabService()
        svc._project = MagicMock()
        svc._project.repository_tree.side_effect = gitlab.exceptions.GitlabGetError(
            response_code=404, error_message="not found"
        )
        result = await svc.list_apis("acme")
        assert result == []


class TestGetFile:
    async def test_not_connected(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_file("path/to/file.txt")

    async def test_found(self):
        svc = GitLabService()
        svc._project = MagicMock()
        mock_file = MagicMock()
        mock_file.decode.return_value = b"content here"
        svc._project.files.get.return_value = mock_file
        result = await svc.get_file("path/to/file.txt")
        assert result == "content here"

    async def test_not_found(self):
        import gitlab

        svc = GitLabService()
        svc._project = MagicMock()
        svc._project.files.get.side_effect = gitlab.exceptions.GitlabGetError(
            response_code=404, error_message="not found"
        )
        result = await svc.get_file("nonexistent")
        assert result is None


class TestGetFullTreeRecursive:
    async def test_not_connected(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_full_tree_recursive()

    async def test_returns_tree(self):
        svc = GitLabService()
        svc._project = MagicMock()
        tree_data = [{"path": "tenants/acme/apis/weather/api.yaml", "type": "blob"}]
        svc._project.repository_tree.return_value = tree_data
        result = await svc.get_full_tree_recursive("tenants")
        assert result == tree_data
        svc._project.repository_tree.assert_called_once_with(
            path="tenants", ref="main", recursive=True, per_page=1000, all=True
        )


# ── _fetch_with_protection ──


class TestFetchWithProtection:
    async def test_success(self):
        async def factory():
            return "ok"

        result = await _fetch_with_protection(factory, "test")
        assert result == "ok"

    async def test_timeout_retries(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                await asyncio.sleep(100)
            return "ok"

        with pytest.raises(TimeoutError):
            await _fetch_with_protection(factory, "test", timeout=0.01, max_retries=2)
        assert call_count == 2

    async def test_rate_limit_retry(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 Too Many Requests")
            return "ok"

        result = await _fetch_with_protection(factory, "test", max_retries=3)
        assert result == "ok"
        assert call_count == 2

    async def test_non_retryable_error(self):
        async def factory():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await _fetch_with_protection(factory, "test")


class TestGitLabRateLimitError:
    def test_is_exception(self):
        err = GitLabRateLimitError("rate limit")
        assert isinstance(err, Exception)
        assert str(err) == "rate limit"
