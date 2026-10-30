"""Authentication and tenant isolation for the tenant skills routes."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

ROUTES = [
    ("get", "/v1/tenants/acme/skills", None),
    ("post", "/v1/tenants/acme/skills", {"name": "probe", "scope": "tenant"}),
    ("get", "/v1/tenants/acme/skills/resolve", None),
]


@pytest.fixture
def reached():
    calls: list[str] = []

    async def fake(self, *args, **kwargs):
        calls.append("repo")
        return []

    async def fake_count(self, *args, **kwargs):
        calls.append("repo")
        return 0

    base = "src.routers.skills.SkillRepository"
    with (
        patch(f"{base}.create", fake),
        patch(f"{base}.list_by_tenant", fake),
        patch(f"{base}.count_by_tenant", fake_count),
        patch(f"{base}.list_resolved", fake),
        patch(f"{base}.get", fake),
        patch(f"{base}.update", fake),
        patch(f"{base}.delete", fake),
    ):
        yield calls


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES, ids=["list", "create", "resolve"])
def test_anonymous_request_is_refused(client, reached, verb, url, body):
    response = getattr(client, verb)(url) if body is None else getattr(client, verb)(url, json=body)
    assert response.status_code == 401, (response.status_code, reached)
    assert reached == []


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES, ids=["list", "create", "resolve"])
def test_other_tenant_is_refused(client_as_other_tenant, reached, verb, url, body):
    c = client_as_other_tenant
    response = getattr(c, verb)(url) if body is None else getattr(c, verb)(url, json=body)
    assert response.status_code == 403, (response.status_code, reached)
    assert reached == []


SKILL_URL = f"/v1/tenants/acme/skills/{uuid4()}"
ALL_ROUTES = [
    *ROUTES,
    ("get", SKILL_URL, None),
    ("patch", SKILL_URL, {"name": "probe"}),
    ("delete", SKILL_URL, None),
]
ALL_IDS = ["list", "create", "resolve", "get", "update", "delete"]


@pytest.mark.parametrize(("verb", "url", "body"), ALL_ROUTES, ids=ALL_IDS)
def test_anonymous_request_is_refused_on_every_route(client, reached, verb, url, body):
    response = getattr(client, verb)(url) if body is None else getattr(client, verb)(url, json=body)
    assert response.status_code == 401, (response.status_code, reached)
    assert reached == []


@pytest.mark.parametrize(("verb", "url", "body"), ALL_ROUTES, ids=ALL_IDS)
def test_other_tenant_is_refused_on_every_route(client_as_other_tenant, reached, verb, url, body):
    c = client_as_other_tenant
    response = getattr(c, verb)(url) if body is None else getattr(c, verb)(url, json=body)
    assert response.status_code == 403, (response.status_code, reached)
    assert reached == []


def test_own_tenant_reaches_repository(client_as_tenant_admin, reached):
    response = client_as_tenant_admin.get("/v1/tenants/acme/skills/resolve")
    assert response.status_code == 200
    assert reached
