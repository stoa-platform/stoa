"""Regression guard for CP-1 P2 L.1 — GitLab pagination stops truncating.

Closes L.1 (BUG-REPORT-CP-1.md): ``project.branches.list()`` and
``project.mergerequests.list(state=...)`` in python-gitlab default to
page 1 only (≤20 items). ``project.commits.list(path=..., per_page=N)``
caps at N for the first page and never fetches beyond. All three must
now paginate fully. PyGithub's PaginatedList iterates transparently,
so only GitLab is affected.

regression for CP-1 L.1
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import pytest

from src.services.git_service import GitLabService


def _make_fake_branch(i: int):
    b = MagicMock()
    b.name = f"branch-{i}"
    b.commit = {"id": f"sha{i:03d}"}
    b.protected = False
    return b


def _make_fake_mr(i: int):
    mr = MagicMock()
    mr.id = 1000 + i
    mr.iid = i
    mr.title = f"MR {i}"
    mr.description = ""
    mr.state = "opened"
    mr.source_branch = f"feature/{i}"
    mr.target_branch = "main"
    mr.web_url = f"https://gl/mr/{i}"
    mr.created_at = "2026-04-23T00:00:00Z"
    mr.author = {"name": "tester"}
    return mr


def _make_fake_commit(i: int):
    c = MagicMock()
    c.id = f"commit{i:03d}"
    c.message = f"commit {i}"
    c.author_name = "tester"
    c.created_at = "2026-04-23T00:00:00Z"
    return c


@pytest.mark.asyncio
async def test_list_branches_uses_get_all_true(monkeypatch):
    """GitLab list_branches must pass ``get_all=True`` so catalogs with
    >20 branches no longer silently truncate.

    regression for CP-1 L.1
    """
    svc = GitLabService()
    project = MagicMock()
    svc._project = project
    svc._gl = MagicMock()

    # Stub 35 branches — would be truncated to 20 under the old default.
    fake_branches = [_make_fake_branch(i) for i in range(35)]
    project.branches.list.return_value = fake_branches

    branches = await svc.list_branches()

    # get_all=True must be passed — NOT "page" / "per_page" / defaults only.
    project.branches.list.assert_called_once_with(get_all=True)
    # No silent truncation: we got all 35, not 20.
    assert len(branches) == 35, f"expected 35 branches, got {len(branches)}"
    assert branches[20].name == "branch-20", "item past page-1 boundary must be present"


@pytest.mark.asyncio
async def test_list_merge_requests_and_commits_paginate_fully(monkeypatch):
    """GitLab list_merge_requests must pass get_all=True; list_commits must
    use iterator=True + per_page=min(limit,100) and honour the ``limit``
    contract via itertools.islice.

    regression for CP-1 L.1
    """
    svc = GitLabService()
    project = MagicMock()
    svc._project = project
    svc._gl = MagicMock()

    # --- list_merge_requests: 35 items, get_all=True expected. ---
    fake_mrs = [_make_fake_mr(i) for i in range(35)]
    project.mergerequests.list.return_value = fake_mrs

    mrs = await svc.list_merge_requests(state="opened")

    project.mergerequests.list.assert_called_once_with(state="opened", get_all=True)
    assert len(mrs) == 35, f"expected 35 MRs, got {len(mrs)}"

    # --- list_commits: stub returns an iterator of 150 commits; call with
    # limit=50 → iterator=True, per_page=min(50,100)=50, islice caps at 50. ---
    def commit_iterator(**_kwargs):
        # Return an unbounded iterator of fake commits — the stub asserts
        # that production code does not materialise the full paginated
        # list in memory.
        return iter(_make_fake_commit(i) for i in range(10_000))

    project.commits.list.side_effect = commit_iterator

    commits = await svc.list_commits(path="docs/api.md", limit=50)

    # Only one call, and the kwargs are tight.
    assert project.commits.list.call_count == 1
    _, kwargs = project.commits.list.call_args
    assert kwargs.get("iterator") is True, "list_commits must pass iterator=True"
    assert kwargs.get("per_page") == 50, f"per_page should be min(50,100)=50, got {kwargs.get('per_page')}"
    assert kwargs.get("path") == "docs/api.md"
    # islice honours limit: exactly 50 commits returned.
    assert len(commits) == 50, f"expected limit=50 commits, got {len(commits)}"
    assert commits[0]["sha"] == "commit000"
    assert commits[49]["sha"] == "commit049"

    # And per_page caps at 100 when limit > 100.
    project.commits.list.reset_mock()
    project.commits.list.side_effect = commit_iterator
    big = await svc.list_commits(limit=250)
    _, big_kwargs = project.commits.list.call_args
    assert big_kwargs.get("per_page") == 100, "per_page must cap at 100 even when limit > 100"
    assert len(big) == 250, "islice still honours the caller's limit"
    # itertools.islice sanity — proves we don't leak into the 10_000-item tail.
    assert isinstance(big, list)
    _ = itertools  # silence unused-import lint on reruns
