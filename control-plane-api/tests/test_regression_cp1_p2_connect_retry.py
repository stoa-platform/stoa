"""Regression guard for CP-1 P2 M.5 — connect() retries transient errors.

Closes M.5 (BUG-REPORT-CP-1.md): ``connect()`` on both providers retries
transient failures (network errors, TimeoutError, 5xx, 429) with
1s → 2s exponential backoff over 3 attempts. Authentication errors
(401/403) fail fast — retrying them is pointless and costly.

regression for CP-1 M.5
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import gitlab.exceptions
import pytest
import requests.exceptions
from github import BadCredentialsException, GithubException

import sys

from src.services.git_service import GitLabService
from src.services.github_service import GitHubService

# `src.services.git_service` is shadowed in the package namespace by the
# `git_service` GitLabService instance re-exported from __init__.py — go
# through sys.modules to reach the actual module for monkeypatching.
git_service_mod = sys.modules["src.services.git_service"]
github_service_mod = sys.modules["src.services.github_service"]


@pytest.mark.asyncio
async def test_gitlab_connect_retries_on_transient_and_succeeds(monkeypatch):
    """GitLab connect: 2 ConnectionError then success → 3 attempts,
    sleeps 1s then 2s. Auth error → no retry.

    regression for CP-1 M.5
    """
    svc = GitLabService()

    # Part 1: transient path.
    successful_tuple = (MagicMock(), MagicMock(name="project"), "catalog-repo")

    call_count = {"n": 0}

    async def fake_gl_run(fn, op_name, timeout=15.0):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise requests.exceptions.ConnectionError("network down")
        return successful_tuple

    sleep_mock = AsyncMock()
    monkeypatch.setattr(git_service_mod, "_gl_run", fake_gl_run)
    monkeypatch.setattr(git_service_mod.asyncio, "sleep", sleep_mock)
    # settings.git.gitlab must have a token; the closure is never actually
    # executed because _gl_run is patched, but the method reads gl_cfg first.
    monkeypatch.setattr(
        git_service_mod.settings.git.gitlab.token,
        "get_secret_value",
        lambda: "fake-token",
    )

    await svc.connect()

    assert call_count["n"] == 3, "must retry exactly until success (3 attempts)"
    assert sleep_mock.call_args_list == [((1,),), ((2,),)], (
        f"expected sleeps of 1s then 2s, got {sleep_mock.call_args_list}"
    )
    assert svc._gl is successful_tuple[0]

    # Part 2: auth error fails fast. Reset state.
    svc2 = GitLabService()
    auth_call_count = {"n": 0}

    async def fake_gl_run_auth(fn, op_name, timeout=15.0):  # type: ignore[no-untyped-def]
        auth_call_count["n"] += 1
        raise gitlab.exceptions.GitlabAuthenticationError("bad token", response_code=401)

    sleep_mock_auth = AsyncMock()
    monkeypatch.setattr(git_service_mod, "_gl_run", fake_gl_run_auth)
    monkeypatch.setattr(git_service_mod.asyncio, "sleep", sleep_mock_auth)

    with pytest.raises(gitlab.exceptions.GitlabAuthenticationError):
        await svc2.connect()

    assert auth_call_count["n"] == 1, "must fail fast on auth error (no retry)"
    assert sleep_mock_auth.call_count == 0, "must NOT sleep on auth error"


@pytest.mark.asyncio
async def test_github_connect_retries_on_transient_and_succeeds(monkeypatch):
    """GitHub connect: 2 ConnectionError then success → 3 attempts,
    sleeps 1s then 2s. Bad credentials → no retry.

    regression for CP-1 M.5
    """
    svc = GitHubService()
    successful_tuple = (MagicMock(), "octocat")

    call_count = {"n": 0}

    async def fake_gh_read(fn, op_name, timeout=15.0):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise requests.exceptions.ConnectionError("network down")
        return successful_tuple

    sleep_mock = AsyncMock()
    monkeypatch.setattr(github_service_mod, "_gh_read", fake_gh_read)
    monkeypatch.setattr(github_service_mod.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(
        github_service_mod.settings.git.github.token,
        "get_secret_value",
        lambda: "fake-gh-token",
    )

    await svc.connect()

    assert call_count["n"] == 3, "must retry exactly until success (3 attempts)"
    assert sleep_mock.call_args_list == [((1,),), ((2,),)], (
        f"expected sleeps of 1s then 2s, got {sleep_mock.call_args_list}"
    )
    assert svc._gh is successful_tuple[0]

    # Part 2: bad credentials fails fast.
    svc2 = GitHubService()
    auth_call_count = {"n": 0}

    async def fake_gh_read_auth(fn, op_name, timeout=15.0):  # type: ignore[no-untyped-def]
        auth_call_count["n"] += 1
        raise BadCredentialsException(401, {"message": "Bad credentials"}, {})

    sleep_mock_auth = AsyncMock()
    monkeypatch.setattr(github_service_mod, "_gh_read", fake_gh_read_auth)
    monkeypatch.setattr(github_service_mod.asyncio, "sleep", sleep_mock_auth)

    with pytest.raises(BadCredentialsException):
        await svc2.connect()

    assert auth_call_count["n"] == 1, "must fail fast on credential error (no retry)"
    assert sleep_mock_auth.call_count == 0, "must NOT sleep on credential error"

    # Sanity: 5xx is retried (uses same classifier).
    call_count_5xx = {"n": 0}

    async def fake_gh_read_5xx(fn, op_name, timeout=15.0):  # type: ignore[no-untyped-def]
        call_count_5xx["n"] += 1
        if call_count_5xx["n"] == 1:
            raise GithubException(503, {"message": "Service unavailable"}, {})
        return successful_tuple

    sleep_mock_5xx = AsyncMock()
    svc3 = GitHubService()
    monkeypatch.setattr(github_service_mod, "_gh_read", fake_gh_read_5xx)
    monkeypatch.setattr(github_service_mod.asyncio, "sleep", sleep_mock_5xx)

    await svc3.connect()
    assert call_count_5xx["n"] == 2, "5xx is transient; must retry once"
    assert sleep_mock_5xx.call_args_list == [((1,),)]
