"""Regression guard for CP-1 P2 M.4 — default branch resolved at boundary.

Closes M.4 (BUG-REPORT-CP-1.md): provider methods that used to hardcode
``ref="main"`` / ``branch="main"`` now resolve ``None`` to
``settings.git.default_branch`` at the method boundary. Callers that
omit ``ref`` must hit the configured default, not the hardcoded ``"main"``.

regression for CP-1 M.4
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config import settings
from src.services.git_service import GitLabService
from src.services.github_service import GitHubService


@pytest.mark.asyncio
async def test_gitlab_list_tenants_uses_configured_default_branch(monkeypatch):
    """GitLab list_tenants must call ``repository_tree(..., ref=default_branch)``
    with the configured default, not hardcoded ``"main"``.

    regression for CP-1 M.4
    """
    monkeypatch.setattr(settings.git, "default_branch", "develop")

    svc = GitLabService()
    project = MagicMock()
    project.repository_tree.return_value = [
        {"name": "acme", "type": "tree"},
        {"name": "globex", "type": "tree"},
    ]
    svc._project = project
    svc._gl = MagicMock()

    tenants = await svc.list_tenants()

    assert tenants == ["acme", "globex"]
    project.repository_tree.assert_called_once_with(path="tenants", ref="develop")
    # No call should have used the old hardcoded literal.
    for _, kwargs in project.repository_tree.call_args_list:
        assert kwargs.get("ref") != "main", "old hardcoded ref=main leaked through"


@pytest.mark.asyncio
async def test_github_list_apis_uses_configured_default_branch(monkeypatch):
    """GitHub list_apis must call ``get_contents(base_path, ref=default_branch)``
    with the configured default, not hardcoded ``"main"``.

    regression for CP-1 M.4
    """
    monkeypatch.setattr(settings.git, "default_branch", "trunk")

    svc = GitHubService()
    gh = MagicMock()
    svc._gh = gh

    repo = MagicMock()
    repo.get_contents.return_value = []  # empty tenant/apis directory
    gh.get_repo.return_value = repo

    apis = await svc.list_apis("acme")

    assert apis == []
    repo.get_contents.assert_called_once()
    _, kwargs = repo.get_contents.call_args
    assert kwargs.get("ref") == "trunk", f"expected ref=trunk, got {kwargs.get('ref')}"
