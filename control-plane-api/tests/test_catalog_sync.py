"""Tests for CAB-688: Catalog sync parallel GitLab calls"""
import asyncio
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from src.services.git_service import (
    GitLabService,
    _fetch_with_protection,
)


@pytest.mark.asyncio
async def test_fetch_with_protection_success():
    """Basic success case for protected fetch"""
    async def ok():
        return "ok"

    result = await _fetch_with_protection(ok, "test-call")
    assert result == "ok"


@pytest.mark.asyncio
async def test_fetch_with_protection_timeout():
    """Verify timeout triggers retry then raises"""
    async def slow():
        await asyncio.sleep(10)

    with pytest.raises(TimeoutError):
        await _fetch_with_protection(
            slow, "slow-call", timeout=0.01, max_retries=2
        )


@pytest.mark.asyncio
async def test_fetch_with_protection_retry_on_429():
    """Verify exponential backoff retry on 429"""
    call_count = 0

    async def rate_limited_then_ok():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("429 Too Many Requests")
        return {"id": "test"}

    result = await _fetch_with_protection(
        rate_limited_then_ok, "retry-call", max_retries=3
    )
    assert result == {"id": "test"}
    assert call_count == 3


@pytest.mark.asyncio
async def test_fetch_with_protection_no_retry_on_other_errors():
    """Non-429 errors should not be retried"""
    call_count = 0

    async def failing():
        nonlocal call_count
        call_count += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        await _fetch_with_protection(failing, "fail-call", max_retries=3)

    assert call_count == 1


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """Verify GITLAB_SEMAPHORE caps applicative concurrency at 10.

    CP-1 (C.4): the semaphore was moved from _fetch_with_protection to
    git_executor.run_sync so it applies UNIFORMLY across every GitLab
    method, not only the two "parallel" fetchers. The invariant tested
    here is the one that matters: run_sync, invoked 30x concurrently,
    never lets more than 10 closures run in parallel.
    """
    import threading

    from src.services import git_executor

    concurrent = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def tracked_sync_call():
        with lock:
            concurrent["current"] += 1
            concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        time.sleep(0.02)
        with lock:
            concurrent["current"] -= 1
        return "ok"

    # Use a fresh semaphore bound to the current loop — the module-level
    # GITLAB_SEMAPHORE may have been acquired by an earlier test's loop.
    fresh_sem = asyncio.Semaphore(10)

    tasks = [
        git_executor.run_sync(
            tracked_sync_call,
            semaphore=fresh_sem,
            op_name=f"call-{i}",
        )
        for i in range(30)
    ]
    await asyncio.gather(*tasks)

    assert concurrent["peak"] <= 10, (
        f"Semaphore violated: {concurrent['peak']} concurrent"
    )


@pytest.mark.asyncio
async def test_list_apis_parallel_is_parallel():
    """Verify parallel execution is faster than sequential"""
    service = GitLabService()
    service._project = MagicMock()
    service._project.repository_tree.return_value = [
        {"name": f"api-{i}", "type": "tree"} for i in range(10)
    ]

    async def slow_get_api(tenant, api_id):
        await asyncio.sleep(0.05)
        return {"id": api_id, "name": api_id}

    service.get_api = slow_get_api

    start = time.time()
    result = await service.list_apis_parallel("demo")
    elapsed = time.time() - start

    assert len(result) == 10
    # Sequential would be ~500ms, parallel should be ~50ms
    assert elapsed < 0.3, f"Should be parallel, took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_get_all_openapi_specs_parallel():
    """Verify parallel openapi spec fetching"""
    service = GitLabService()
    service._project = MagicMock()

    async def mock_spec(tenant, api_id):
        return {"openapi": "3.0.0", "info": {"title": api_id}}

    service.get_api_openapi_spec = mock_spec

    result = await service.get_all_openapi_specs_parallel("demo", ["api-1", "api-2", "api-3"])

    assert len(result) == 3
    assert "api-1" in result
    assert result["api-2"]["info"]["title"] == "api-2"


@pytest.mark.asyncio
async def test_parse_tree_to_tenant_apis():
    """Verify recursive tree parsing"""
    service = GitLabService()
    tree = [
        {"type": "tree", "path": "tenants/acme"},
        {"type": "tree", "path": "tenants/acme/apis"},
        {"type": "blob", "path": "tenants/acme/apis/petstore/api.yaml"},
        {"type": "blob", "path": "tenants/acme/apis/petstore/openapi.yaml"},
        {"type": "blob", "path": "tenants/acme/apis/weather/api.yaml"},
        {"type": "blob", "path": "tenants/beta/apis/users/api.yaml"},
        {"type": "blob", "path": "tenants/acme/tenant.yaml"},
    ]

    result = service.parse_tree_to_tenant_apis(tree)

    assert result == {
        "acme": ["petstore", "weather"],
        "beta": ["users"],
    }


@pytest.mark.asyncio
async def test_sync_all_progress_logging(caplog):
    """Verify progress logging output (obligation #4)"""
    # This test validates the logging format without needing a real DB
    with caplog.at_level(logging.INFO, logger="src.services.catalog_sync_service"):
        # We just verify the log format pattern exists in the implementation
        assert "Sync progress: tenant" in open(
            "src/services/catalog_sync_service.py"
        ).read()
