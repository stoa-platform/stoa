"""Smoke tests verifying GIT_PROVIDER=github returns GitHubService (CAB-1890).

These tests complement the parametrized tests in test_git_service.py by
verifying the factory + config integration at a high level. They run
quickly and catch misconfiguration early.
"""

from unittest.mock import patch

import pytest

from src.services.git_provider import GitProvider, get_git_provider, git_provider_factory


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """Clear the lru_cache before each test so factory re-reads settings."""
    get_git_provider.cache_clear()
    yield
    get_git_provider.cache_clear()


class TestGitHubProviderSmoke:
    """Verify GIT_PROVIDER=github creates a valid GitHubService."""

    def test_factory_github_returns_github_service(self, monkeypatch):
        monkeypatch.setenv("GIT_PROVIDER", "github")
        with patch("src.services.git_provider.settings") as mock_settings:
            mock_settings.GIT_PROVIDER = "github"
            provider = git_provider_factory()
        from src.services.github_service import GitHubService

        assert isinstance(provider, GitHubService)
        assert isinstance(provider, GitProvider)

    def test_factory_gitlab_returns_gitlab_service(self, monkeypatch):
        monkeypatch.setenv("GIT_PROVIDER", "gitlab")
        with patch("src.services.git_provider.settings") as mock_settings:
            mock_settings.GIT_PROVIDER = "gitlab"
            mock_settings.GITLAB_URL = "https://gitlab.example.com"
            mock_settings.GITLAB_TOKEN = "test-token"
            mock_settings.GITLAB_PROJECT_ID = "12345"
            provider = git_provider_factory()
        from src.services.git_service import GitLabService

        assert isinstance(provider, GitLabService)
        assert isinstance(provider, GitProvider)


class TestGitHubProviderDisconnect:
    """Verify GitHubService disconnect is safe without connect."""

    @pytest.mark.asyncio
    async def test_github_disconnect_without_connect(self):
        from src.services.github_service import GitHubService

        svc = GitHubService()
        await svc.disconnect()  # should not raise
        assert svc._gh is None

    @pytest.mark.asyncio
    async def test_github_not_connected_raises(self):
        from src.services.github_service import GitHubService

        svc = GitHubService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_repo_info("org/repo")


class TestDefaultProviderIsGitLab:
    """Verify the default GIT_PROVIDER in Settings is 'gitlab'."""

    def test_settings_default(self):
        from src.config import Settings

        field = Settings.model_fields["GIT_PROVIDER"]
        assert field.default == "gitlab"
