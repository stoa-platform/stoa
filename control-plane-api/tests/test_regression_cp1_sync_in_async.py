"""Regression guards for CP-1 C.1/C.4/C.5/C.6.

Closes:
- C.1 (sync-in-async blocks event loop)
- C.4 (GitLab semaphore not applied uniformly)
- C.5 (GitHub has no applicative concurrency cap)
- C.6 (write_file TOCTOU via _file_exists pre-check)

These tests pin the invariants enforced by services/git_executor.py and
the migration of GitLabService / GitHubService to route every sync SDK
call through ``run_sync``.

regression for CP-1 C.1
regression for CP-1 C.4
regression for CP-1 C.5
regression for CP-1 C.6
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.services import git_executor
from src.services.git_service import GitLabService
from src.services.github_service import GitHubService


def _make_gitlab_service() -> GitLabService:
    """Build a minimally-wired GitLabService whose _project/_gl are mocks."""
    svc = GitLabService()
    svc._gl = MagicMock()
    svc._project = MagicMock()
    return svc


def _make_github_service() -> GitHubService:
    """Build a minimally-wired GitHubService whose _gh is a mock."""
    svc = GitHubService()
    svc._gh = MagicMock()
    return svc


# ──────────────────────────────────────────────────────────────────
# C.1 — event loop stays responsive under concurrent sync SDK calls
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_read_does_not_starve_event_loop():
    """Heartbeat stays alive while 10 sync reads run in parallel.

    Without run_sync's offload, 10 x 200ms blocking reads monopolise the
    loop for 2s and the heartbeat cannot tick. With offload, all 10 go
    to threads and the heartbeat ticks freely.
    """
    svc = _make_github_service()

    def _blocking_get_contents(path, ref):
        time.sleep(0.2)
        fake = MagicMock()
        fake.decoded_content = b"hello"
        return fake

    repo = MagicMock()
    repo.get_contents.side_effect = _blocking_get_contents
    svc._gh.get_repo.return_value = repo

    heartbeat = {"ticks": 0}
    stop = False

    async def _beat():
        while not stop:
            heartbeat["ticks"] += 1
            await asyncio.sleep(0.01)

    beat_task = asyncio.create_task(_beat())

    start = time.monotonic()
    await asyncio.gather(*[svc.get_file_content("org/repo", f"f{i}") for i in range(10)])
    elapsed = time.monotonic() - start

    stop = True
    await asyncio.sleep(0)
    beat_task.cancel()

    # With 10-way parallel offload, wall clock should be far below serial 2s.
    # Loose upper bound to avoid CI flakes on thread-pool lazy-init.
    assert elapsed < 1.5, f"wall clock {elapsed:.2f}s suggests serial execution"
    # Heartbeat should have ticked many times during the window.
    # At 10ms cadence over ~200ms we expect at least 10 ticks in practice.
    assert heartbeat["ticks"] >= 10, f"heartbeat only ticked {heartbeat['ticks']} times"


# ──────────────────────────────────────────────────────────────────
# C.5 / C.6 — GitHub Contents write semaphore serialises (cap=1)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_contents_write_semaphore_serialises():
    """5 concurrent create_file calls must run strictly one at a time."""
    svc = _make_github_service()

    concurrent = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def _create_file(*args, **kwargs):
        with lock:
            concurrent["current"] += 1
            concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        time.sleep(0.05)
        with lock:
            concurrent["current"] -= 1
        return {"commit": MagicMock(sha="abc", html_url="http://x")}

    repo = MagicMock()
    repo.create_file.side_effect = _create_file
    svc._gh.get_repo.return_value = repo

    await asyncio.gather(
        *[svc.create_file("org/repo", f"f{i}.txt", "hello", "msg") for i in range(5)]
    )

    assert concurrent["peak"] == 1, (
        f"Contents writes must serialise — observed peak concurrency {concurrent['peak']}"
    )


# ──────────────────────────────────────────────────────────────────
# C.5 — GitHub meta-write semaphore caps at 5
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_meta_write_semaphore_caps_at_5():
    """10 concurrent create_webhook calls must peak at <= 5 in parallel."""
    svc = _make_github_service()

    concurrent = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def _create_hook(*args, **kwargs):
        with lock:
            concurrent["current"] += 1
            concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        time.sleep(0.05)
        with lock:
            concurrent["current"] -= 1
        hook = MagicMock()
        hook.id = 1
        hook.config = {"url": "http://x"}
        return hook

    repo = MagicMock()
    repo.create_hook.side_effect = _create_hook
    svc._gh.get_repo.return_value = repo

    await asyncio.gather(
        *[svc.create_webhook("org/repo", f"http://h{i}", "secret", ["push"]) for i in range(10)]
    )

    assert concurrent["peak"] <= 5, (
        f"Meta-write concurrency must be capped at 5 — observed peak {concurrent['peak']}"
    )


# ──────────────────────────────────────────────────────────────────
# C.1 — per-call timeout enforced via run_sync
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_timeout_enforced():
    """run_sync must raise TimeoutError when the sync call exceeds timeout.

    We exercise the helper directly because the per-call timeout is a
    structural guarantee of run_sync — every service method routes its
    sync SDK call through this helper, so the enforcement proven here
    covers every migrated call site.
    """

    def _hang():
        time.sleep(5.0)
        return "never"

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await git_executor.run_sync(
            _hang,
            semaphore=git_executor.GITHUB_READ_SEMAPHORE,
            timeout=0.2,
            op_name="test.timeout",
        )
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"timeout should fire around 0.2s, took {elapsed:.2f}s"


# ──────────────────────────────────────────────────────────────────
# C.6 — write_file has NO _file_exists pre-check (no TOCTOU window)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_write_file_no_toctou_github():
    """write_file on GitHub must call create_file first, never _file_exists.

    The pre-existing code did:
        if await self._file_exists(...): update_file(...)
        else: create_file(...)
    which opens a TOCTOU window. The fix pattern is:
        try: create_file(...)
        except ValueError: update_file(...)
    """
    svc = _make_github_service()

    # _file_exists must NOT be called by write_file. create_file raises
    # "already exists"; update_file should be the fallback path.
    with (
        patch.object(svc, "_file_exists", new=MagicMock(side_effect=AssertionError("must not be called"))),
        patch.object(svc, "create_file", side_effect=ValueError("File already exists: foo")) as mocked_create,
        patch.object(svc, "update_file", return_value={"sha": "1", "url": "u"}) as mocked_update,
    ):
        result = await svc.write_file("foo.txt", "content", "msg")

    assert result == "updated"
    mocked_create.assert_called_once()
    mocked_update.assert_called_once()


@pytest.mark.asyncio
async def test_regression_cp1_write_file_no_toctou_gitlab():
    """Same invariant for GitLab's write_file."""
    svc = _make_gitlab_service()

    # GitLab write_file's prior implementation used get_file → exists check → save or create.
    # New pattern delegates to create_file → falls through to update_file on ValueError.
    with (
        patch.object(svc, "create_file", side_effect=ValueError("File already exists: foo")) as mocked_create,
        patch.object(svc, "update_file", return_value={"sha": "1", "url": "u"}) as mocked_update,
    ):
        result = await svc.write_file("foo.txt", "content", "msg")

    assert result == "updated"
    mocked_create.assert_called_once()
    mocked_update.assert_called_once()


@pytest.mark.asyncio
async def test_regression_cp1_write_file_first_write_returns_created():
    """write_file returns 'created' on the happy path where the file is new."""
    svc = _make_github_service()
    with (
        patch.object(svc, "create_file", return_value={"sha": "1", "url": "u"}) as mocked_create,
        patch.object(svc, "update_file") as mocked_update,
    ):
        result = await svc.write_file("new.txt", "content", "msg")

    assert result == "created"
    mocked_create.assert_called_once()
    mocked_update.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# C.4 — GITLAB_SEMAPHORE applied uniformly across methods
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regression_cp1_gitlab_semaphore_uniform():
    """3 different read methods must all acquire the single GITLAB_SEMAPHORE.

    Inflates concurrency: with cap 10 and 20 requests spanning 3 method types,
    observed peak must stay <= 10.
    """
    svc = _make_gitlab_service()

    concurrent = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def _slow_op(*args, **kwargs):
        with lock:
            concurrent["current"] += 1
            concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        time.sleep(0.03)
        with lock:
            concurrent["current"] -= 1
        return MagicMock()

    # Make every sync SDK surface path increment the counter.
    def _slow_list(*_a: object, **_kw: object) -> list:
        _slow_op()
        return []

    def _slow_get(*_a: object, **_kw: object) -> MagicMock:
        return _slow_op()

    svc._project.repository_tree.side_effect = _slow_list
    svc._project.files.get.side_effect = _slow_get
    svc._project.commits.list.side_effect = _slow_list
    svc._gl.projects.get.return_value = svc._project

    # Fire across 3 methods.
    coros = []
    for _ in range(7):
        coros.append(svc.list_tenants())
    for _ in range(7):
        coros.append(svc.list_commits(path="x"))
    for _ in range(6):
        coros.append(svc.list_tree("x"))

    await asyncio.gather(*coros, return_exceptions=True)

    assert concurrent["peak"] <= 10, (
        f"GitLab applicative cap violated — observed peak {concurrent['peak']}"
    )


# ──────────────────────────────────────────────────────────────────
# Implementation-rule regression — PaginatedList materialised in thread
# ──────────────────────────────────────────────────────────────────


class _FakePaginatedList:
    """Simulates PyGithub PaginatedList with synchronous per-fetch sleeps."""

    def __init__(self, items, fetch_delay=0.05):
        self._items = items
        self._fetch_delay = fetch_delay

    def __iter__(self):
        for item in self._items:
            time.sleep(self._fetch_delay)
            yield item


@pytest.mark.asyncio
async def test_regression_cp1_paginated_list_materialised_in_thread():
    """Iterating a PaginatedList must happen inside run_sync, not after await.

    If iteration leaked to the event loop, the heartbeat would freeze while
    list_branches runs.
    """
    svc = _make_github_service()

    def _make_branch(name):
        b = MagicMock()
        b.name = name
        b.commit.sha = f"sha-{name}"
        b.protected = False
        return b

    repo = MagicMock()
    # get_branches returns a PaginatedList-like; each iteration step sleeps.
    repo.get_branches.return_value = _FakePaginatedList(
        [_make_branch(f"b{i}") for i in range(5)], fetch_delay=0.04
    )
    svc._gh.get_repo.return_value = repo

    heartbeat = {"ticks": 0}
    stop = False

    async def _beat():
        while not stop:
            heartbeat["ticks"] += 1
            await asyncio.sleep(0.01)

    beat_task = asyncio.create_task(_beat())
    result = await svc.list_branches()
    stop = True
    await asyncio.sleep(0)
    beat_task.cancel()

    assert len(result) == 5
    # Iteration window is ~5 * 40ms = 200ms; at 10ms beat cadence we expect
    # at least 8 ticks if iteration happened in a thread.
    assert heartbeat["ticks"] >= 8, (
        f"heartbeat froze during iteration — only {heartbeat['ticks']} ticks "
        "(suggests PaginatedList iteration leaked onto the event loop)"
    )
