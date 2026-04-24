"""Regression guard for CP-1 P2 M.2 — idempotent merge_merge_request.

Closes M.2 (BUG-REPORT-CP-1.md): ``merge_merge_request`` on both providers
must short-circuit when the target PR/MR is **already merged**, but must
NOT short-circuit on "closed but unmerged" — those still fall through to
``pr.merge()`` / ``mr.merge()`` and surface the provider error.

regression for CP-1 M.2
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.git_service import GitLabService
from src.services.github_service import GitHubService


@pytest.mark.asyncio
async def test_github_merge_request_short_circuits_when_already_merged(monkeypatch):
    """GitHub: ``pr.merged is True`` → no pr.merge() call; closed-unmerged
    still calls pr.merge() and raises.

    regression for CP-1 M.2
    """
    svc = GitHubService()
    gh = MagicMock()
    svc._gh = gh

    # Case 1 — PR already merged. Expect NO pr.merge() call, ref returned
    # reflects the already-merged state.
    merged_pr = MagicMock()
    merged_pr.merged = True
    merged_pr.id = 42
    merged_pr.number = 7
    merged_pr.title = "already merged PR"
    merged_pr.body = "payload"
    merged_pr.state = "closed"
    merged_pr.head = MagicMock(ref="feature/x")
    merged_pr.base = MagicMock(ref="main")
    merged_pr.html_url = "https://gh/pr/7"
    merged_pr.created_at = None
    merged_pr.user = MagicMock(login="alice")

    repo = MagicMock()
    repo.get_pull.return_value = merged_pr
    gh.get_repo.return_value = repo

    ref = await svc.merge_merge_request(7)

    assert ref.iid == 7
    assert ref.state == "closed"
    assert merged_pr.merge.call_count == 0, "pr.merge() must not run when already merged"
    # Single get_pull call: we did NOT re-fetch because we short-circuited.
    assert repo.get_pull.call_count == 1

    # Case 2 — PR closed but NOT merged. Must fall through to pr.merge()
    # and propagate its error. Proves the short-circuit is narrow.
    closed_unmerged = MagicMock()
    closed_unmerged.merged = False
    closed_unmerged.merge.side_effect = RuntimeError("provider rejects merge of closed PR")

    repo2 = MagicMock()
    repo2.get_pull.return_value = closed_unmerged
    gh.get_repo.return_value = repo2

    with pytest.raises(RuntimeError, match="provider rejects merge of closed PR"):
        await svc.merge_merge_request(7)

    assert closed_unmerged.merge.call_count == 1, "closed-unmerged must still call pr.merge()"


@pytest.mark.asyncio
async def test_gitlab_merge_request_short_circuits_when_already_merged(monkeypatch):
    """GitLab: ``mr.state == "merged"`` → no mr.merge() call; closed-unmerged
    still calls mr.merge() and raises.

    regression for CP-1 M.2
    """
    svc = GitLabService()
    project = MagicMock()
    svc._project = project
    svc._gl = MagicMock()

    # Case 1 — MR already merged.
    merged_mr = MagicMock()
    merged_mr.state = "merged"
    merged_mr.id = 100
    merged_mr.iid = 13
    merged_mr.title = "done MR"
    merged_mr.description = "payload"
    merged_mr.source_branch = "feature/y"
    merged_mr.target_branch = "main"
    merged_mr.web_url = "https://gl/mr/13"
    merged_mr.created_at = "2026-04-20T10:00:00Z"
    merged_mr.author = {"name": "bob"}

    project.mergerequests.get.return_value = merged_mr

    ref = await svc.merge_merge_request(13)

    assert ref.iid == 13
    assert ref.state == "merged"
    assert merged_mr.merge.call_count == 0, "mr.merge() must not run when already merged"

    # Case 2 — MR closed-unmerged. Must call mr.merge() and propagate.
    closed_mr = MagicMock()
    closed_mr.state = "closed"
    closed_mr.merge.side_effect = RuntimeError("provider rejects merge of closed MR")

    project.mergerequests.get.return_value = closed_mr

    with pytest.raises(RuntimeError, match="provider rejects merge of closed MR"):
        await svc.merge_merge_request(13)

    assert closed_mr.merge.call_count == 1, "closed-unmerged must still call mr.merge()"
