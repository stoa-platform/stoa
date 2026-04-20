"""Regression coverage for CAB-1889 GitHub override lookup."""

from unittest.mock import AsyncMock
from unittest.mock import patch

from src.services.github_service import GitHubService


async def test_regression_cab_1889_github_override_lookup_uses_catalog_repo():
    """GitHub mode must not fall back to the injected GitLab project id."""
    svc = GitHubService()
    svc.get_file_content = AsyncMock(return_value="rateLimit: 25\n")

    with patch("src.services.git_provider.settings") as mock_settings:
        mock_settings.GIT_PROVIDER = "github"
        mock_settings.GITLAB_PROJECT_ID = "12345"
        mock_settings.GITHUB_ORG = "stoa-platform"
        mock_settings.GITHUB_CATALOG_REPO = "stoa-catalog"

        override = await svc.get_api_override("banking-demo", "fapi-banking", "prod")

    assert override == {"rateLimit": 25}
    svc.get_file_content.assert_awaited_once_with(
        "stoa-platform/stoa-catalog",
        "tenants/banking-demo/apis/fapi-banking/overrides/prod.yaml",
    )
