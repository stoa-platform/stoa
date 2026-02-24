"""Unit tests for GitLabService and module-level helpers.

Covers:
- Constants (GITLAB_SEMAPHORE, GITLAB_TIMEOUT, GITLAB_MAX_RETRIES)
- _normalize_api_data (simple and K8s-style formats)
- _normalize_mcp_server_data (full data, minimal, tool defaults, tool missing name)
- Path helpers (_get_tenant_path, _get_api_path, _get_mcp_server_path)
- parse_tree_to_tenant_apis (empty, blobs-only, multi-tenant)
- connect / disconnect
- get_tenant (found, not found, not connected)
- _ensure_tenant_exists (exists, not exists → auto-creates)
- _api_exists (exists, not exists)
- create_tenant_structure (success, not connected, exception propagation)
- create_api (success, duplicate via ValueError, GitlabCreateError already-exists, not connected)
- get_api (found, not found, YAML error, not connected)
- get_api_openapi_spec (yaml found, json found, all missing, exception)
- update_api (success, not connected, exception propagation)
- delete_api (success with files, empty tree, not connected)
- list_apis (success, gitlab 404 returns [], not connected)
- list_apis_parallel (success, empty tree, individual failure is skipped)
- get_all_openapi_specs_parallel (success, individual failure returns None)
- get_full_tree_recursive (success, not connected)
- get_file (found, not found, not connected)
- list_commits (success)
- get_mcp_server (found, not found, YAML error, not connected)
- list_mcp_servers (platform, tenant, empty/404, not connected)
- list_all_mcp_servers (platform + tenant servers, tenants 404, not connected)
- create_mcp_server (success, already exists, not connected, exception propagation)
- update_mcp_server (success, field mapping, not connected, exception propagation)
- delete_mcp_server (success with actions, empty tree, not connected)
- _fetch_with_protection (success, timeout retry, 429 retry, non-retryable break)
- GitLabRateLimitError
"""
import asyncio
from unittest.mock import MagicMock, patch

import gitlab
import pytest
import yaml

from src.services.git_service import (
    GITLAB_MAX_RETRIES,
    GITLAB_SEMAPHORE,
    GITLAB_TIMEOUT,
    GitLabRateLimitError,
    GitLabService,
    _fetch_with_protection,
    _normalize_api_data,
)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _connected_service() -> GitLabService:
    """Return a GitLabService with a mocked _project already set."""
    svc = GitLabService()
    svc._project = MagicMock()
    svc._gl = MagicMock()
    return svc


def _mock_file(content: str | bytes) -> MagicMock:
    """Return a file mock whose .decode() returns the given content."""
    mock_file = MagicMock()
    if isinstance(content, str):
        content = content.encode()
    mock_file.decode.return_value = content
    return mock_file


def _gitlab_get_error(code: int = 404) -> gitlab.exceptions.GitlabGetError:
    return gitlab.exceptions.GitlabGetError(response_code=code, error_message="not found")


def _gitlab_create_error(msg: str = "already exists") -> gitlab.exceptions.GitlabCreateError:
    return gitlab.exceptions.GitlabCreateError(response_code=409, error_message=msg)


# ─────────────────────────────────────────────
# Module-level constants
# ─────────────────────────────────────────────


class TestConstants:
    def test_semaphore_limit_is_ten(self):
        assert GITLAB_SEMAPHORE._value == 10

    def test_timeout_is_five_seconds(self):
        assert GITLAB_TIMEOUT == 5.0

    def test_max_retries_is_three(self):
        assert GITLAB_MAX_RETRIES == 3


# ─────────────────────────────────────────────
# _normalize_api_data
# ─────────────────────────────────────────────


class TestNormalizeApiData:
    def test_simple_format_returned_as_is(self):
        raw = {"id": "api-1", "name": "My API", "status": "active"}
        result = _normalize_api_data(raw)
        assert result is raw

    def test_k8s_format_full(self):
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

    def test_k8s_format_defaults(self):
        raw = {"apiVersion": "v1", "kind": "API", "metadata": {}, "spec": {}}
        result = _normalize_api_data(raw)
        assert result["id"] == ""
        assert result["version"] == "1.0.0"
        assert result["status"] == "draft"
        assert result["backend_url"] == ""
        assert result["deployments"]["dev"] is False
        assert result["deployments"]["staging"] is False

    def test_k8s_display_name_fallback_to_metadata_name(self):
        raw = {
            "apiVersion": "v1",
            "kind": "API",
            "metadata": {"name": "test-api"},
            "spec": {},
        }
        result = _normalize_api_data(raw)
        assert result["display_name"] == "test-api"

    def test_k8s_explicit_display_name_wins(self):
        raw = {
            "apiVersion": "v1",
            "kind": "API",
            "metadata": {"name": "test-api"},
            "spec": {"displayName": "Pretty Name"},
        }
        result = _normalize_api_data(raw)
        assert result["display_name"] == "Pretty Name"

    def test_k8s_only_apiVersion_required(self):
        """Both apiVersion and kind must be present for K8s branch."""
        raw = {"apiVersion": "v1", "name": "api"}  # no kind
        result = _normalize_api_data(raw)
        # Falls through to simple format
        assert result is raw


# ─────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────


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


# ─────────────────────────────────────────────
# _normalize_mcp_server_data
# ─────────────────────────────────────────────


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
        tool = result["tools"][0]
        assert tool["name"] == "search"
        assert tool["display_name"] == "Search Tool"
        assert tool["method"] == "GET"
        assert tool["requires_approval"] is True
        assert tool["input_schema"] == {"type": "object"}
        assert tool["timeout"] == "60s"
        assert tool["rate_limit"] == 30
        backend = result["backend"]
        assert backend["base_url"] == "http://search:9200"
        assert backend["auth_type"] == "bearer"
        assert backend["secret_ref"] == "search-token"
        assert backend["timeout"] == "10s"
        assert backend["retries"] == 5

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
        assert tool["display_name"] == "tool-1"
        assert tool["method"] == "POST"
        assert tool["enabled"] is True
        assert tool["requires_approval"] is False
        assert tool["timeout"] == "30s"
        assert tool["rate_limit"] == 60

    def test_tool_missing_name_included_as_none(self):
        raw = {
            "metadata": {"name": "svc"},
            "spec": {"tools": [{"description": "no name here"}]},
        }
        result = self.svc._normalize_mcp_server_data(raw, "path")
        assert result["tools"][0]["name"] is None

    def test_git_path_set(self):
        raw = {"metadata": {"name": "svc"}, "spec": {}}
        result = self.svc._normalize_mcp_server_data(raw, "some/git/path")
        assert result["git_path"] == "some/git/path"


# ─────────────────────────────────────────────
# parse_tree_to_tenant_apis
# ─────────────────────────────────────────────


class TestParseTreeToTenantApis:
    def setup_method(self):
        self.svc = GitLabService()

    def test_empty_tree(self):
        assert self.svc.parse_tree_to_tenant_apis([]) == {}

    def test_ignores_non_blob_entries(self):
        tree = [{"type": "tree", "path": "tenants/acme/apis/weather"}]
        assert self.svc.parse_tree_to_tenant_apis(tree) == {}

    def test_parses_api_yaml_blobs(self):
        tree = [
            {"type": "blob", "path": "tenants/acme/apis/weather/api.yaml"},
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

    def test_ignores_non_api_yaml_blobs(self):
        tree = [
            {"type": "blob", "path": "tenants/acme/apis/weather/openapi.yaml"},
            {"type": "blob", "path": "tenants/acme/tenant.yaml"},
        ]
        assert self.svc.parse_tree_to_tenant_apis(tree) == {}


# ─────────────────────────────────────────────
# connect / disconnect
# ─────────────────────────────────────────────


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

    async def test_connect_clears_state_on_failure(self):
        svc = GitLabService()
        with patch("src.services.git_service.settings") as mock_settings:
            mock_settings.GITLAB_URL = "https://gitlab.example.com"
            mock_settings.GITLAB_TOKEN = "token"
            mock_settings.GITLAB_PROJECT_ID = 1
            with patch("src.services.git_service.gitlab.Gitlab", side_effect=RuntimeError("boom")):
                with pytest.raises(RuntimeError):
                    await svc.connect()
        # _project should never have been set
        assert svc._project is None


class TestDisconnect:
    async def test_disconnect_clears_both_refs(self):
        svc = GitLabService()
        svc._gl = MagicMock()
        svc._project = MagicMock()
        await svc.disconnect()
        assert svc._gl is None
        assert svc._project is None

    async def test_disconnect_idempotent_when_already_none(self):
        svc = GitLabService()
        await svc.disconnect()  # should not raise
        assert svc._gl is None
        assert svc._project is None


# ─────────────────────────────────────────────
# get_tenant
# ─────────────────────────────────────────────


class TestGetTenant:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_tenant("acme")

    async def test_found_returns_parsed_yaml(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file("id: acme\nname: ACME Corp\n")
        result = await svc.get_tenant("acme")
        assert result["id"] == "acme"
        assert result["name"] == "ACME Corp"

    async def test_not_found_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.get_tenant("unknown")
        assert result is None

    async def test_requests_correct_path(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file("id: t1\n")
        await svc.get_tenant("t1")
        svc._project.files.get.assert_called_once_with(
            "tenants/t1/tenant.yaml", ref="main"
        )


# ─────────────────────────────────────────────
# _ensure_tenant_exists
# ─────────────────────────────────────────────


class TestEnsureTenantExists:
    async def test_existing_tenant_returns_true(self):
        svc = _connected_service()
        svc._project.files.get.return_value = MagicMock()
        result = await svc._ensure_tenant_exists("acme")
        assert result is True

    async def test_missing_tenant_creates_structure(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        svc._project.commits.create.return_value = MagicMock()
        result = await svc._ensure_tenant_exists("new-tenant")
        assert result is True
        svc._project.commits.create.assert_called_once()


# ─────────────────────────────────────────────
# create_tenant_structure
# ─────────────────────────────────────────────


class TestCreateTenantStructure:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.create_tenant_structure("acme", {})

    async def test_success_creates_commit(self):
        svc = _connected_service()
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.create_tenant_structure("acme", {"name": "ACME"})
        assert result is True
        svc._project.commits.create.assert_called_once()
        call_args = svc._project.commits.create.call_args[0][0]
        assert call_args["branch"] == "main"
        assert "Create tenant acme" in call_args["commit_message"]
        file_paths = [a["file_path"] for a in call_args["actions"]]
        assert "tenants/acme/tenant.yaml" in file_paths
        assert "tenants/acme/apis/.gitkeep" in file_paths
        assert "tenants/acme/applications/.gitkeep" in file_paths

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.commits.create.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.create_tenant_structure("acme", {})

    async def test_uses_provided_name(self):
        svc = _connected_service()
        svc._project.commits.create.return_value = MagicMock()
        await svc.create_tenant_structure("acme", {"name": "ACME Corp", "display_name": "ACME"})
        call_args = svc._project.commits.create.call_args[0][0]
        content = call_args["actions"][0]["content"]
        assert "ACME Corp" in content


# ─────────────────────────────────────────────
# create_api
# ─────────────────────────────────────────────


class TestCreateApi:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.create_api("acme", {"name": "my-api"})

    async def test_success_returns_api_name(self):
        svc = _connected_service()
        # _ensure_tenant_exists: file exists
        svc._project.files.get.side_effect = [
            MagicMock(),      # tenant.yaml exists
            _gitlab_get_error(),  # api.yaml not found → api does not exist
        ]
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.create_api("acme", {"name": "weather", "id": "weather-id"})
        assert result == "weather-id"

    async def test_success_uses_name_as_id_when_id_not_provided(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),
            _gitlab_get_error(),
        ]
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.create_api("acme", {"name": "weather"})
        assert result == "weather"

    async def test_duplicate_api_raises_value_error(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),   # tenant.yaml exists
            MagicMock(),   # api.yaml exists → duplicate
        ]
        with pytest.raises(ValueError, match="already exists"):
            await svc.create_api("acme", {"name": "weather"})

    async def test_creates_commit_with_api_yaml_and_policies_gitkeep(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),
            _gitlab_get_error(),
        ]
        svc._project.commits.create.return_value = MagicMock()
        await svc.create_api("acme", {"name": "billing"})
        call_args = svc._project.commits.create.call_args[0][0]
        file_paths = [a["file_path"] for a in call_args["actions"]]
        assert "tenants/acme/apis/billing/api.yaml" in file_paths
        assert "tenants/acme/apis/billing/policies/.gitkeep" in file_paths

    async def test_includes_openapi_spec_when_provided(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),
            _gitlab_get_error(),
        ]
        svc._project.commits.create.return_value = MagicMock()
        await svc.create_api("acme", {"name": "billing", "openapi_spec": "openapi: 3.0.0"})
        call_args = svc._project.commits.create.call_args[0][0]
        file_paths = [a["file_path"] for a in call_args["actions"]]
        assert "tenants/acme/apis/billing/openapi.yaml" in file_paths

    async def test_gitlab_create_error_already_exists_raises_value_error(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),
            _gitlab_get_error(),
        ]
        svc._project.commits.create.side_effect = _gitlab_create_error("already exists")
        with pytest.raises(ValueError, match="already exists"):
            await svc.create_api("acme", {"name": "weather"})

    async def test_other_exception_propagates(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            MagicMock(),
            _gitlab_get_error(),
        ]
        svc._project.commits.create.side_effect = RuntimeError("network error")
        with pytest.raises(RuntimeError, match="network error"):
            await svc.create_api("acme", {"name": "weather"})


# ─────────────────────────────────────────────
# get_api
# ─────────────────────────────────────────────


class TestGetApi:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_api("acme", "weather")

    async def test_returns_normalized_data(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file("id: weather\nname: Weather API\n")
        result = await svc.get_api("acme", "weather")
        assert result["id"] == "weather"

    async def test_not_found_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.get_api("acme", "unknown")
        assert result is None

    async def test_yaml_error_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file(b": invalid yaml ][")
        result = await svc.get_api("acme", "bad")
        assert result is None

    async def test_requests_correct_path(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file("id: w\n")
        await svc.get_api("acme", "weather")
        svc._project.files.get.assert_called_once_with(
            "tenants/acme/apis/weather/api.yaml", ref="main"
        )


# ─────────────────────────────────────────────
# get_api_openapi_spec
# ─────────────────────────────────────────────


class TestGetApiOpenapiSpec:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_api_openapi_spec("acme", "weather")

    async def test_returns_yaml_spec(self):
        svc = _connected_service()
        spec_yaml = "openapi: '3.0.0'\ninfo:\n  title: Test\n"
        svc._project.files.get.return_value = _mock_file(spec_yaml)
        result = await svc.get_api_openapi_spec("acme", "weather")
        assert result is not None
        assert result["openapi"] == "3.0.0"

    async def test_falls_back_to_yml_when_yaml_missing(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = [
            _gitlab_get_error(),  # openapi.yaml not found
            _mock_file("openapi: '3.0.0'\n"),  # openapi.yml found
        ]
        result = await svc.get_api_openapi_spec("acme", "weather")
        assert result is not None

    async def test_returns_none_when_all_missing(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.get_api_openapi_spec("acme", "weather")
        assert result is None

    async def test_exception_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = RuntimeError("unexpected")
        result = await svc.get_api_openapi_spec("acme", "weather")
        assert result is None


# ─────────────────────────────────────────────
# update_api
# ─────────────────────────────────────────────


class TestUpdateApi:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.update_api("acme", "weather", {})

    async def test_success_returns_true(self):
        svc = _connected_service()
        mock_file = _mock_file("id: weather\nname: Old Name\n")
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        result = await svc.update_api("acme", "weather", {"name": "New Name"})
        assert result is True
        mock_file.save.assert_called_once_with(branch="main", commit_message="Update API weather")

    async def test_content_updated_before_save(self):
        svc = _connected_service()
        original_yaml = yaml.dump({"id": "w", "status": "draft"})
        mock_file = _mock_file(original_yaml)
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        await svc.update_api("acme", "weather", {"status": "published"})
        new_content = yaml.safe_load(mock_file.content)
        assert new_content["status"] == "published"

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.update_api("acme", "weather", {})


# ─────────────────────────────────────────────
# delete_api
# ─────────────────────────────────────────────


class TestDeleteApi:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.delete_api("acme", "weather")

    async def test_success_deletes_all_blobs(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "blob", "path": "tenants/acme/apis/weather/api.yaml"},
            {"type": "blob", "path": "tenants/acme/apis/weather/openapi.yaml"},
            {"type": "tree", "path": "tenants/acme/apis/weather/policies"},
        ]
        svc._project.files.delete = MagicMock()
        result = await svc.delete_api("acme", "weather")
        assert result is True
        assert svc._project.files.delete.call_count == 2

    async def test_empty_tree_succeeds(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = []
        svc._project.files.delete = MagicMock()
        result = await svc.delete_api("acme", "weather")
        assert result is True
        svc._project.files.delete.assert_not_called()

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.delete_api("acme", "weather")


# ─────────────────────────────────────────────
# list_apis
# ─────────────────────────────────────────────


class TestListApis:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_apis("acme")

    async def test_returns_empty_list_on_404(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = _gitlab_get_error()
        result = await svc.list_apis("acme")
        assert result == []

    async def test_skips_gitkeep_entries(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": ".gitkeep"},
            {"type": "blob", "name": "not-a-dir"},
        ]
        result = await svc.list_apis("acme")
        assert result == []

    async def test_fetches_each_api_by_name(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": "weather"},
            {"type": "tree", "name": "billing"},
        ]
        svc._project.files.get.return_value = _mock_file("id: x\nname: X\n")
        result = await svc.list_apis("acme")
        assert len(result) == 2

    async def test_skips_api_when_get_returns_none(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": "bad-api"},
        ]
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.list_apis("acme")
        assert result == []


# ─────────────────────────────────────────────
# list_apis_parallel
# ─────────────────────────────────────────────


class TestListApisParallel:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_apis_parallel("acme")

    async def test_returns_empty_on_404(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = _gitlab_get_error()
        result = await svc.list_apis_parallel("acme")
        assert result == []

    async def test_fetches_all_api_dirs_in_parallel(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": "weather"},
            {"type": "tree", "name": "billing"},
            {"type": "blob", "name": "file.txt"},  # ignored
        ]
        svc._project.files.get.return_value = _mock_file("id: x\nname: X\n")
        result = await svc.list_apis_parallel("acme")
        assert len(result) == 2

    async def test_skips_gitkeep_in_parallel(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": ".gitkeep"},
        ]
        result = await svc.list_apis_parallel("acme")
        assert result == []

    async def test_failed_individual_fetch_skipped(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": "ok-api"},
            {"type": "tree", "name": "bad-api"},
        ]
        call_count = {"n": 0}
        original_get_api = svc.get_api

        async def patched_get_api(tenant_id, api_id):
            call_count["n"] += 1
            if api_id == "bad-api":
                raise RuntimeError("fetch failure")
            return {"id": api_id, "name": api_id}

        svc.get_api = patched_get_api
        result = await svc.list_apis_parallel("acme")
        assert len(result) == 1
        assert result[0]["id"] == "ok-api"


# ─────────────────────────────────────────────
# get_all_openapi_specs_parallel
# ─────────────────────────────────────────────


class TestGetAllOpenapiSpecsParallel:
    async def test_returns_specs_for_all_ids(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file("openapi: '3.0.0'\n")
        result = await svc.get_all_openapi_specs_parallel("acme", ["weather", "billing"])
        assert set(result.keys()) == {"weather", "billing"}
        assert result["weather"] is not None

    async def test_failed_individual_fetch_yields_none(self):
        svc = _connected_service()
        call_count = {"n": 0}
        original = svc.get_api_openapi_spec

        async def patched(tenant_id, api_id):
            call_count["n"] += 1
            if api_id == "bad":
                raise RuntimeError("fail")
            return {"openapi": "3.0.0"}

        svc.get_api_openapi_spec = patched
        result = await svc.get_all_openapi_specs_parallel("acme", ["ok", "bad"])
        assert result["bad"] is None
        assert result["ok"] is not None

    async def test_returns_empty_dict_for_no_ids(self):
        svc = _connected_service()
        result = await svc.get_all_openapi_specs_parallel("acme", [])
        assert result == {}


# ─────────────────────────────────────────────
# get_full_tree_recursive
# ─────────────────────────────────────────────


class TestGetFullTreeRecursive:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_full_tree_recursive()

    async def test_returns_tree(self):
        svc = _connected_service()
        tree_data = [{"path": "tenants/acme/apis/weather/api.yaml", "type": "blob"}]
        svc._project.repository_tree.return_value = tree_data
        result = await svc.get_full_tree_recursive("tenants")
        assert result == tree_data
        svc._project.repository_tree.assert_called_once_with(
            path="tenants", ref="main", recursive=True, per_page=1000, all=True
        )

    async def test_default_path_is_tenants(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = []
        await svc.get_full_tree_recursive()
        call_kwargs = svc._project.repository_tree.call_args[1]
        assert call_kwargs["path"] == "tenants"


# ─────────────────────────────────────────────
# get_file
# ─────────────────────────────────────────────


class TestGetFile:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_file("path/to/file.txt")

    async def test_found_returns_decoded_string(self):
        svc = _connected_service()
        mock_file = MagicMock()
        mock_file.decode.return_value = b"content here"
        svc._project.files.get.return_value = mock_file
        result = await svc.get_file("path/to/file.txt")
        assert result == "content here"

    async def test_not_found_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.get_file("nonexistent")
        assert result is None


# ─────────────────────────────────────────────
# list_commits
# ─────────────────────────────────────────────


class TestListCommits:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_commits()

    async def test_returns_formatted_commits(self):
        svc = _connected_service()
        mock_commit = MagicMock()
        mock_commit.id = "abc123"
        mock_commit.message = "feat: add thing"
        mock_commit.author_name = "Alice"
        mock_commit.created_at = "2026-01-01T00:00:00Z"
        svc._project.commits.list.return_value = [mock_commit]
        result = await svc.list_commits(path="tenants/acme", limit=10)
        assert len(result) == 1
        assert result[0]["sha"] == "abc123"
        assert result[0]["message"] == "feat: add thing"
        assert result[0]["author"] == "Alice"

    async def test_default_limit_is_twenty(self):
        svc = _connected_service()
        svc._project.commits.list.return_value = []
        await svc.list_commits()
        svc._project.commits.list.assert_called_once_with(path=None, per_page=20)


# ─────────────────────────────────────────────
# get_mcp_server
# ─────────────────────────────────────────────


class TestGetMcpServer:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_mcp_server("acme", "my-server")

    async def test_found_returns_normalized_data(self):
        svc = _connected_service()
        raw = yaml.dump({"metadata": {"name": "my-server"}, "spec": {}})
        svc._project.files.get.return_value = _mock_file(raw)
        result = await svc.get_mcp_server("acme", "my-server")
        assert result is not None
        assert result["name"] == "my-server"

    async def test_not_found_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        result = await svc.get_mcp_server("acme", "unknown")
        assert result is None

    async def test_yaml_error_returns_none(self):
        svc = _connected_service()
        svc._project.files.get.return_value = _mock_file(b": invalid: [yaml")
        result = await svc.get_mcp_server("acme", "bad")
        assert result is None

    async def test_platform_server_uses_platform_path(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        await svc.get_mcp_server("_platform", "plat-svc")
        call_path = svc._project.files.get.call_args[0][0]
        assert call_path == "platform/mcp-servers/plat-svc/server.yaml"


# ─────────────────────────────────────────────
# list_mcp_servers
# ─────────────────────────────────────────────


class TestListMcpServers:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_mcp_servers("acme")

    async def test_platform_path(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = []
        await svc.list_mcp_servers("_platform")
        svc._project.repository_tree.assert_called_once_with(
            path="platform/mcp-servers", ref="main"
        )

    async def test_tenant_path(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = []
        await svc.list_mcp_servers("acme")
        svc._project.repository_tree.assert_called_once_with(
            path="tenants/acme/mcp-servers", ref="main"
        )

    async def test_returns_empty_list_on_404(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = _gitlab_get_error()
        result = await svc.list_mcp_servers("acme")
        assert result == []

    async def test_skips_gitkeep_entries(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": ".gitkeep"},
        ]
        result = await svc.list_mcp_servers("acme")
        assert result == []

    async def test_fetches_each_server(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "name": "search"},
            {"type": "tree", "name": "analytics"},
        ]
        raw = yaml.dump({"metadata": {"name": "x"}, "spec": {}})
        svc._project.files.get.return_value = _mock_file(raw)
        result = await svc.list_mcp_servers("acme")
        assert len(result) == 2


# ─────────────────────────────────────────────
# list_all_mcp_servers
# ─────────────────────────────────────────────


class TestListAllMcpServers:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.list_all_mcp_servers()

    async def test_combines_platform_and_tenant_servers(self):
        svc = _connected_service()
        raw = yaml.dump({"metadata": {"name": "svc"}, "spec": {}})

        # First call: platform servers tree → 1 server
        # Second call: tenants tree → 1 tenant
        # Third call: tenant servers tree → 1 server
        svc._project.repository_tree.side_effect = [
            [{"type": "tree", "name": "platform-svc"}],  # platform/mcp-servers
            [{"type": "tree", "name": "acme"}],           # tenants
            [{"type": "tree", "name": "tenant-svc"}],     # tenants/acme/mcp-servers
        ]
        svc._project.files.get.return_value = _mock_file(raw)
        result = await svc.list_all_mcp_servers()
        assert len(result) == 2

    async def test_no_tenants_directory_returns_platform_only(self):
        svc = _connected_service()
        raw = yaml.dump({"metadata": {"name": "svc"}, "spec": {}})
        call_count = {"n": 0}
        original_list = svc.list_mcp_servers

        async def patched_list(tenant_id):
            call_count["n"] += 1
            if tenant_id == "_platform":
                return [{"name": "platform-svc"}]
            return []

        svc.list_mcp_servers = patched_list
        svc._project.repository_tree.side_effect = _gitlab_get_error()  # no tenants dir
        result = await svc.list_all_mcp_servers()
        assert len(result) == 1

    async def test_empty_returns_empty_list(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = [
            [],                  # platform/mcp-servers empty
            [],                  # tenants empty
        ]
        result = await svc.list_all_mcp_servers()
        assert result == []


# ─────────────────────────────────────────────
# create_mcp_server
# ─────────────────────────────────────────────


class TestCreateMcpServer:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.create_mcp_server("acme", {"name": "svc"})

    async def test_success_returns_server_name(self):
        svc = _connected_service()
        # get_mcp_server returns None → server does not exist
        svc._project.files.get.side_effect = _gitlab_get_error()
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.create_mcp_server("acme", {"name": "my-server"})
        assert result == "my-server"

    async def test_already_exists_raises_value_error(self):
        svc = _connected_service()
        # get_mcp_server returns something → server exists
        raw = yaml.dump({"metadata": {"name": "my-server"}, "spec": {}})
        svc._project.files.get.return_value = _mock_file(raw)
        with pytest.raises(ValueError, match="already exists"):
            await svc.create_mcp_server("acme", {"name": "my-server"})

    async def test_creates_server_yaml_in_correct_path(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        svc._project.commits.create.return_value = MagicMock()
        await svc.create_mcp_server("acme", {"name": "my-server"})
        call_args = svc._project.commits.create.call_args[0][0]
        file_paths = [a["file_path"] for a in call_args["actions"]]
        assert "tenants/acme/mcp-servers/my-server/server.yaml" in file_paths

    async def test_commit_uses_kubernetes_style_yaml(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        svc._project.commits.create.return_value = MagicMock()
        await svc.create_mcp_server("acme", {
            "name": "my-server",
            "display_name": "My Server",
            "description": "Test",
        })
        call_args = svc._project.commits.create.call_args[0][0]
        content_yaml = yaml.safe_load(call_args["actions"][0]["content"])
        assert content_yaml["apiVersion"] == "gostoa.dev/v1"
        assert content_yaml["kind"] == "MCPServer"
        assert content_yaml["spec"]["displayName"] == "My Server"

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = _gitlab_get_error()
        svc._project.commits.create.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.create_mcp_server("acme", {"name": "my-server"})


# ─────────────────────────────────────────────
# update_mcp_server
# ─────────────────────────────────────────────


class TestUpdateMcpServer:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.update_mcp_server("acme", "my-server", {})

    async def test_success_returns_true(self):
        svc = _connected_service()
        current = yaml.dump({"apiVersion": "v1", "kind": "MCPServer", "metadata": {"name": "svc"}, "spec": {}})
        mock_file = _mock_file(current)
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        result = await svc.update_mcp_server("acme", "svc", {"description": "new desc"})
        assert result is True
        mock_file.save.assert_called_once_with(branch="main", commit_message="Update MCP server svc")

    async def test_updates_display_name_field(self):
        svc = _connected_service()
        current = yaml.dump({"spec": {"displayName": "Old"}})
        mock_file = _mock_file(current)
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        await svc.update_mcp_server("acme", "svc", {"display_name": "New Name"})
        saved = yaml.safe_load(mock_file.content)
        assert saved["spec"]["displayName"] == "New Name"

    async def test_updates_documentation_url_field(self):
        svc = _connected_service()
        current = yaml.dump({"spec": {}})
        mock_file = _mock_file(current)
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        await svc.update_mcp_server("acme", "svc", {"documentation_url": "https://docs.example.com"})
        saved = yaml.safe_load(mock_file.content)
        assert saved["spec"]["documentationUrl"] == "https://docs.example.com"

    async def test_creates_spec_when_missing(self):
        svc = _connected_service()
        current = yaml.dump({"metadata": {"name": "svc"}})  # no spec key
        mock_file = _mock_file(current)
        mock_file.save = MagicMock()
        svc._project.files.get.return_value = mock_file
        await svc.update_mcp_server("acme", "svc", {"description": "test"})
        saved = yaml.safe_load(mock_file.content)
        assert "spec" in saved

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.files.get.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.update_mcp_server("acme", "svc", {})


# ─────────────────────────────────────────────
# delete_mcp_server
# ─────────────────────────────────────────────


class TestDeleteMcpServer:
    async def test_not_connected_raises(self):
        svc = GitLabService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.delete_mcp_server("acme", "my-server")

    async def test_success_creates_delete_commit(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "blob", "path": "tenants/acme/mcp-servers/my-server/server.yaml"},
        ]
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.delete_mcp_server("acme", "my-server")
        assert result is True
        svc._project.commits.create.assert_called_once()
        call_args = svc._project.commits.create.call_args[0][0]
        assert call_args["actions"][0]["action"] == "delete"

    async def test_empty_tree_does_not_create_commit(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = []
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.delete_mcp_server("acme", "my-server")
        assert result is True
        svc._project.commits.create.assert_not_called()

    async def test_skips_tree_entries(self):
        svc = _connected_service()
        svc._project.repository_tree.return_value = [
            {"type": "tree", "path": "tenants/acme/mcp-servers/my-server"},
        ]
        svc._project.commits.create.return_value = MagicMock()
        result = await svc.delete_mcp_server("acme", "my-server")
        assert result is True
        svc._project.commits.create.assert_not_called()

    async def test_exception_propagates(self):
        svc = _connected_service()
        svc._project.repository_tree.side_effect = RuntimeError("git error")
        with pytest.raises(RuntimeError, match="git error"):
            await svc.delete_mcp_server("acme", "my-server")


# ─────────────────────────────────────────────
# _fetch_with_protection
# ─────────────────────────────────────────────


class TestFetchWithProtection:
    async def test_success_returns_value(self):
        async def factory():
            return "ok"

        result = await _fetch_with_protection(factory, "test")
        assert result == "ok"

    async def test_timeout_exhausts_all_retries(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(100)
            return "ok"

        with pytest.raises(TimeoutError):
            await _fetch_with_protection(factory, "test", timeout=0.01, max_retries=2)
        assert call_count == 2

    async def test_rate_limit_429_retries_once(self):
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

    async def test_rate_limit_case_insensitive(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate Limit Exceeded")
            return "ok"

        result = await _fetch_with_protection(factory, "test", max_retries=3)
        assert result == "ok"

    async def test_non_retryable_error_breaks_immediately(self):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await _fetch_with_protection(factory, "test", max_retries=5)
        # Should only call once — non-retryable breaks immediately
        assert call_count == 1

    async def test_exhausted_retries_raises_last_error(self):
        async def factory():
            raise Exception("429 always rate limited")

        with pytest.raises(GitLabRateLimitError):
            await _fetch_with_protection(factory, "test", max_retries=2)


# ─────────────────────────────────────────────
# GitLabRateLimitError
# ─────────────────────────────────────────────


class TestGitLabRateLimitError:
    def test_is_exception_subclass(self):
        err = GitLabRateLimitError("rate limit hit")
        assert isinstance(err, Exception)
        assert str(err) == "rate limit hit"

    def test_can_be_raised_and_caught(self):
        with pytest.raises(GitLabRateLimitError, match="too many"):
            raise GitLabRateLimitError("too many")
