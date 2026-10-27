"""Regression for CAB-2079: CP tenant scope before MCP filtering/aggregation."""

import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.dependencies import User, get_current_user
from src.routers import mcp_proxy

TOOLS = [
    {"name": "b-private", "tenant_id": "tenant-b", "tags": ["b-only", "shared"]},
    {"name": "a-first", "tenant_id": "tenant-a", "tags": ["a-only", "shared"]},
    {"name": "a-second", "tenant_id": "tenant-a", "tags": ["shared"]},
    # Rust ToolDefinition: None is global; serde omits tenant_id for None.
    {"name": "global-absent", "tags": ["global"]},
    {"name": "global-null", "tenant_id": None, "tags": ["global"]},
]
AUTH = {"Authorization": "Bearer synthetic-auth-canary"}
Harness = tuple[TestClient, list[User], list[httpx.Request]]


def persona(role: str = "viewer", tenant: str | None = "tenant-a") -> User:
    return User(id="identity-canary", email="person-canary@example.invalid", username="name-canary",
                roles=[role], tenant_id=tenant)


@pytest.fixture
async def tenant_proxy(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    users = [persona()]
    requests: list[httpx.Request] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=TOOLS)

    async with httpx.AsyncClient(base_url="http://gateway.invalid", transport=httpx.MockTransport(gateway)) as upstream:
        monkeypatch.setattr(mcp_proxy, "_http_client", upstream)
        app = FastAPI()
        app.include_router(mcp_proxy.router)
        app.dependency_overrides[get_current_user] = lambda: users[0]
        with TestClient(app) as client:
            yield client, users, requests


@pytest.mark.parametrize("role", ["viewer", "tenant-admin", "devops", "cpi-admin"])
@pytest.mark.parametrize("requested", ["tenant-b", None, "", "   "])
def test_regression_cab_2079_scope_before_pagination_and_tags(
    tenant_proxy: Harness, role: str, requested: str | None,
) -> None:
    client, users, requests = tenant_proxy
    users[0] = persona(role)
    params = {} if requested is None else {"tenant_id": requested}
    effective = "tenant-b" if role == "cpi-admin" and requested == "tenant-b" else None if role == "cpi-admin" else "tenant-a"
    expected = [tool for tool in TOOLS if effective is None or tool.get("tenant_id") in (None, effective)]
    response = client.get("/v1/mcp/tools", params={**params, "limit": 1}, headers=AUTH)
    assert response.status_code == 200
    assert [tool["name"] for tool in response.json()["tools"]] == [expected[0]["name"]]
    assert response.json()["totalCount"] == len(expected)
    tags = client.get("/v1/mcp/tools/tags", params=params, headers=AUTH)
    assert tags.status_code == 200
    counts: dict[str, int] = {}
    for tool in expected:
        for tag in tool["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    assert tags.json() == {"tags": sorted(counts), "tagCounts": counts}
    assert len(requests) == 2
    assert all(request.headers["X-Tenant-Id"] == "tenant-a" for request in requests)
    categories = client.get("/v1/mcp/tools/categories", params=params, headers=AUTH)
    assert categories.status_code == 200
    assert categories.json() == {"categories": []}
    assert len(requests) == 2  # Categories must not introduce a gateway request.


@pytest.mark.parametrize("tenant", [None, "", "   "])
@pytest.mark.parametrize("endpoint", ["", "/tags", "/categories"])
def test_regression_cab_2079_missing_tenant_refuses_before_gateway(
    tenant_proxy: Harness, tenant: str | None, endpoint: str,
) -> None:
    client, users, requests = tenant_proxy
    users[0] = persona(tenant=tenant)
    response = client.get("/v1/mcp/tools" + endpoint, params={"tenant_id": "tenant-b"}, headers=AUTH)
    assert response.status_code == 403
    assert requests == []


def test_regression_cab_2079_divergence_warning_is_value_blind(
    tenant_proxy: Harness, caplog: pytest.LogCaptureFixture,
) -> None:
    client, _, _ = tenant_proxy
    with caplog.at_level(logging.WARNING, logger="src.auth.rbac"):
        response = client.get("/v1/mcp/tools", params={"tenant_id": "requested-canary\nline-canary"}, headers=AUTH)
    assert response.status_code == 200
    assert [tool["name"] for tool in response.json()["tools"]] == ["a-first", "a-second", "global-absent", "global-null"]
    assert any(record.name == "src.auth.rbac" for record in caplog.records)
    for value in ["requested-canary", "line-canary", "identity-canary", "person-canary", "name-canary", "synthetic-auth-canary"]:
        assert value not in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.auth.rbac"):
        assert client.get("/v1/mcp/tools", headers=AUTH).status_code == 200
    assert not [record for record in caplog.records if record.name == "src.auth.rbac"]


@pytest.mark.parametrize("role", ["viewer", "cpi-admin"])
def test_regression_cab_2079_global_tools_follow_gateway_contract(tenant_proxy: Harness, role: str) -> None:
    """ToolRegistry::list(Some(tenant)) includes global None and matching owners."""
    client, users, _ = tenant_proxy
    users[0] = persona(role)
    response = client.get("/v1/mcp/tools", params={"tenant_id": "tenant-b", "limit": 100}, headers=AUTH)
    assert response.status_code == 200
    expected = {"global-absent", "global-null"} | ({"b-private"} if role == "cpi-admin" else {"a-first", "a-second"})
    assert {tool["name"] for tool in response.json()["tools"]} == expected
    tags = client.get("/v1/mcp/tools/tags", params={"tenant_id": "tenant-b"}, headers=AUTH)
    assert tags.status_code == 200
    assert tags.json()["tagCounts"]["global"] == 2
    assert ("a-only" if role == "cpi-admin" else "b-only") not in tags.json()["tags"]
