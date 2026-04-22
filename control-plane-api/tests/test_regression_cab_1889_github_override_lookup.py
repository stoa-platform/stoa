"""Regression coverage for CAB-1889 GitHub override lookup."""

from unittest.mock import AsyncMock
from unittest.mock import patch

from pydantic import SecretStr

from src.config import GitHubConfig, GitLabConfig, GitProviderConfig
from src.services.github_service import GitHubService


async def test_regression_cab_1889_github_override_lookup_uses_catalog_repo():
    """GitHub mode must not fall back to the injected GitLab project id."""
    svc = GitHubService()
    svc.get_file_content = AsyncMock(return_value="rateLimit: 25\n")

    # CAB-1889 CP-2: the override lookup reads settings.git.active_catalog_project_id,
    # which must resolve to 'org/repo' for GitHub — not to GITLAB_PROJECT_ID,
    # even when the GitLab field is populated.
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
