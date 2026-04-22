"""Focused parity tests for GitHubService catalog reads."""

from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import SecretStr

from src.config import GitHubConfig, GitLabConfig, GitProviderConfig
from src.services.github_service import GitHubService


def _content(name: str, path: str, item_type: str = "dir") -> MagicMock:
    item = MagicMock()
    item.name = name
    item.path = path
    item.type = item_type
    return item


class TestGitHubServiceCatalogParity:
    async def test_get_head_commit_sha_uses_catalog_repo(self):
        svc = GitHubService()
        repo = MagicMock()
        branch = MagicMock()
        branch.commit.sha = "abc123"
        repo.get_branch.return_value = branch

        svc._gh = MagicMock()
        svc._gh.get_repo.return_value = repo

        sha = await svc.get_head_commit_sha()

        assert sha == "abc123"
        svc._gh.get_repo.assert_called_once_with("stoa-platform/stoa-catalog")
        repo.get_branch.assert_called_once_with("main")

    async def test_list_tenants_filters_to_directories(self):
        svc = GitHubService()
        repo = MagicMock()
        repo.get_contents.return_value = [
            _content("banking-demo", "tenants/banking-demo"),
            _content("README.md", "tenants/README.md", item_type="file"),
            _content("oasis", "tenants/oasis"),
        ]

        svc._gh = MagicMock()
        svc._gh.get_repo.return_value = repo

        tenants = await svc.list_tenants()

        assert tenants == ["banking-demo", "oasis"]
        repo.get_contents.assert_called_once_with("tenants", ref="main")

    async def test_get_api_normalizes_kubernetes_style_yaml(self):
        # regression for CAB-2135: spec.tags and spec.category must survive
        # normalization — without them the sync downstream leaves
        # portal_published=False on every Kind=API manifest (the tag set
        # drives the portal promotion flag).
        svc = GitHubService()
        svc.get_file_content = AsyncMock(return_value="""
apiVersion: gostoa.dev/v1
kind: API
metadata:
  name: banking-services-v1-2
  version: 1.2.0
spec:
  displayName: Banking Services
  description: Banking API
  category: banking
  tags:
    - portal:published
    - banking
  backend:
    url: http://banking-mock.demo-banking-mock.svc.cluster.local:8080/api/v1
  deployments:
    dev: true
    staging: false
""")

        api = await svc.get_api("demo", "banking-services-v1-2")

        assert api == {
            "id": "banking-services-v1-2",
            "name": "banking-services-v1-2",
            "display_name": "Banking Services",
            "version": "1.2.0",
            "description": "Banking API",
            "backend_url": "http://banking-mock.demo-banking-mock.svc.cluster.local:8080/api/v1",
            "status": "draft",
            "category": "banking",
            "tags": ["portal:published", "banking"],
            "deployments": {"dev": True, "staging": False},
        }

    async def test_list_mcp_servers_filters_dirs_and_reads_server_yaml(self):
        svc = GitHubService()
        repo = MagicMock()
        repo.get_contents.return_value = [
            _content("banking-demo", "tenants/demo/mcp-servers/banking-demo"),
            _content(".gitkeep", "tenants/demo/mcp-servers/.gitkeep", item_type="file"),
        ]

        svc._gh = MagicMock()
        svc._gh.get_repo.return_value = repo
        svc.get_mcp_server = AsyncMock(
            return_value={
                "name": "banking-demo",
                "tenant_id": "demo",
                "display_name": "Banking Demo",
            }
        )

        servers = await svc.list_mcp_servers("demo")

        assert servers == [
            {
                "name": "banking-demo",
                "tenant_id": "demo",
                "display_name": "Banking Demo",
            }
        ]
        repo.get_contents.assert_called_once_with("tenants/demo/mcp-servers", ref="main")
        svc.get_mcp_server.assert_awaited_once_with("demo", "banking-demo")

    async def test_get_api_override_uses_github_catalog_repo_even_if_gitlab_id_is_present(self):
        svc = GitHubService()
        svc.get_file_content = AsyncMock(return_value="rateLimit: 25\n")

        git_cfg = GitProviderConfig(
            provider="github",
            github=GitHubConfig(org="stoa-platform", catalog_repo="stoa-catalog"),
            gitlab=GitLabConfig(project_id="12345", token=SecretStr("glpat-x")),
        )

        with patch("src.services.git_provider.settings") as mock_settings:
            mock_settings.git = git_cfg

            override = await svc.get_api_override("banking-demo", "fapi-banking", "prod")

        assert override == {"rateLimit": 25}
        svc.get_file_content.assert_awaited_once_with(
            "stoa-platform/stoa-catalog",
            "tenants/banking-demo/apis/fapi-banking/overrides/prod.yaml",
        )
