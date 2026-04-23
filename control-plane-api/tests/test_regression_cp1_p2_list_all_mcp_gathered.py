"""Regression guard for CP-1 P2 M.6 — list_all_mcp_servers fans out.

Closes M.6 (BUG-REPORT-CP-1.md): ``list_all_mcp_servers`` on both providers
must fetch per-tenant MCP server lists via ``asyncio.gather`` rather than
a serial ``for`` loop. With N tenants and per-call latency L, the total
wall time must be closer to L than N*L.

regression for CP-1 M.6
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from src.services.git_service import GitLabService
from src.services.github_service import GitHubService


@pytest.mark.asyncio
async def test_github_list_all_mcp_servers_fans_out_in_parallel(monkeypatch):
    """GitHub list_all_mcp_servers must run per-tenant list_mcp_servers
    concurrently via asyncio.gather, not sequentially.

    regression for CP-1 M.6
    """
    svc = GitHubService()

    per_call_latency = 0.05  # 50 ms
    tenants = ["t1", "t2", "t3", "t4", "t5"]

    async def fake_list_tenants() -> list[str]:
        return tenants

    call_log: list[str] = []

    async def fake_list_mcp_servers(tenant_id: str) -> list[dict]:
        call_log.append(tenant_id)
        await asyncio.sleep(per_call_latency)
        return [{"name": f"{tenant_id}-srv", "tenant_id": tenant_id}]

    monkeypatch.setattr(svc, "list_tenants", fake_list_tenants)
    monkeypatch.setattr(svc, "list_mcp_servers", fake_list_mcp_servers)

    start = time.perf_counter()
    servers = await svc.list_all_mcp_servers()
    elapsed = time.perf_counter() - start

    # Platform scope + 5 tenants = 6 calls → serial would be ≥ 300 ms.
    # Concurrent upper bound: ≈ per_call_latency (one batch), so assert < 2× latency.
    assert elapsed < 2 * per_call_latency, (
        f"expected parallel fan-out (<{2 * per_call_latency}s), got {elapsed:.3f}s"
    )
    # All 5 tenants plus "_platform" visited.
    assert set(call_log) == set(tenants) | {"_platform"}
    # 6 servers total (1 per scope).
    assert len(servers) == 6


@pytest.mark.asyncio
async def test_gitlab_list_all_mcp_servers_fans_out_in_parallel(monkeypatch):
    """GitLab list_all_mcp_servers must run per-tenant list_mcp_servers
    concurrently via asyncio.gather, not sequentially.

    regression for CP-1 M.6
    """
    from unittest.mock import MagicMock

    svc = GitLabService()
    # Minimal stub: _require_project + _gl_run for tenant enumeration.
    project = MagicMock()
    project.repository_tree.return_value = [
        {"name": f"t{i}", "type": "tree"} for i in range(1, 6)
    ]
    svc._project = project
    svc._gl = MagicMock()

    per_call_latency = 0.05

    call_log: list[str] = []

    async def fake_list_mcp_servers(tenant_id: str = "_platform") -> list[dict]:
        call_log.append(tenant_id)
        await asyncio.sleep(per_call_latency)
        return [{"name": f"{tenant_id}-srv", "tenant_id": tenant_id}]

    monkeypatch.setattr(svc, "list_mcp_servers", fake_list_mcp_servers)

    start = time.perf_counter()
    servers = await svc.list_all_mcp_servers()
    elapsed = time.perf_counter() - start

    # Platform + 5 tenants = 6 awaits → serial ≥ 300 ms; parallel ≈ 50 ms.
    assert elapsed < 2 * per_call_latency, (
        f"expected parallel fan-out (<{2 * per_call_latency}s), got {elapsed:.3f}s"
    )
    assert set(call_log) == {f"t{i}" for i in range(1, 6)} | {"_platform"}
    assert len(servers) == 6
