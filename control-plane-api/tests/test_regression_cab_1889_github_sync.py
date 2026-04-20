"""Regression test for CAB-1889: catalog sync must not deref GitLab `_project`.

PR: #2439
Ticket: CAB-1889
Root cause: `CatalogSyncService` and `MCP GitOps router` dereferenced
  `git._project` (a `python-gitlab` Project object) regardless of provider.
  After flipping `GIT_PROVIDER=github` on prod (via stoa-infra#46), every
  catalog sync failed with `AttributeError: 'GitHubService' object has no
  attribute '_project'`, blocking CAB-2088 banking-demo visibility.
Invariant: provider-neutral methods (`is_connected`, `get_head_commit_sha`,
  `get_tenant`, `list_tenants`) must be used instead of `_project` deref,
  so `GIT_PROVIDER=github` works end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.git_provider import GitProvider
from src.services.github_service import GitHubService


def _content(name: str, path: str, type_: str = "dir") -> MagicMock:
    item = MagicMock()
    item.name = name
    item.path = path
    item.type = type_
    return item


def test_regression_cab_1889_github_service_has_no_project_attr():
    """GitHubService must not expose the GitLab-specific `_project` attribute.

    Any caller still relying on `_project` needs to migrate to the provider-
    neutral interface (is_connected / get_head_commit_sha / get_tenant /
    list_tenants) — see scope boundary in PR #2439 description.
    """
    svc = GitHubService()
    assert not hasattr(svc, "_project"), (
        "GitHubService must not define `_project` (GitLab-only artefact). "
        "If a code path needs it, add a provider-neutral method on GitProvider."
    )


def test_regression_cab_1889_provider_neutral_contract():
    """GitProvider abstract must expose the provider-neutral methods."""
    required = {
        "is_connected",
        "get_head_commit_sha",
        "get_tenant",
        "list_tenants",
    }
    missing = required - set(dir(GitProvider))
    assert not missing, (
        f"GitProvider abstract missing provider-neutral methods: {missing}. "
        "These are required so CatalogSyncService / MCP GitOps router stay "
        "provider-agnostic and CAB-1889 regression doesn't return."
    )


@pytest.mark.asyncio
async def test_regression_cab_1889_github_list_tenants_no_project_deref():
    """GitHubService.list_tenants must work without touching `_project`.

    Validates the fix path: CatalogSyncService iterates tenants via
    `list_tenants()`, not via `_project.repository_tree()`.
    """
    svc = GitHubService()
    repo = MagicMock()
    repo.get_contents.return_value = [
        _content("banking-demo", "tenants/banking-demo"),
        _content("oasis", "tenants/oasis"),
        _content("tenant.yaml", "tenants/tenant.yaml", type_="file"),
    ]
    svc._gh = MagicMock()
    svc._gh.get_repo.return_value = repo

    tenants = await svc.list_tenants()
    assert "banking-demo" in tenants
    assert "oasis" in tenants
    # file entries must not appear as tenants
    assert "tenant.yaml" not in tenants
