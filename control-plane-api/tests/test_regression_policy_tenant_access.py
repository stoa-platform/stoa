"""Native policy authorization; DB/Kafka spies observe reads and effects, not SQL isolation."""

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyScope, PolicyType
from src.routers import gateway_policies as routes

BASE = "/v1/admin/policies"
PID = UUID("10000000-0000-4000-8000-000000000001")
BID = UUID("20000000-0000-4000-8000-000000000001")
OPS = {
    "create": ("POST", BASE, {"name": "sample", "policy_type": "cors"}, 201),
    "list": ("GET", BASE, None, 200),
    "get": ("GET", f"{BASE}/{PID}", None, 200),
    "update": ("PUT", f"{BASE}/{PID}", {"name": "updated"}, 200),
    "delete": ("DELETE", f"{BASE}/{PID}", None, 204),
    "bind": ("POST", BASE + "/bindings", {"policy_id": str(PID)}, 201),
    "unbind": ("DELETE", f"{BASE}/bindings/{BID}", None, 204),
    "bindings": ("GET", f"{BASE}/{PID}/bindings", None, 200),
}
TENANT_OPS = [op for op in OPS if op != "delete"]


def policy(tenant: str | None) -> GatewayPolicy:
    now = datetime.now(UTC)
    return GatewayPolicy(id=PID, name="sample", description=None, tenant_id=tenant, policy_type=PolicyType.CORS,
                         scope=PolicyScope.API, config={}, priority=100, enabled=True, bindings=[],
                         created_at=now, updated_at=now)


def binding(tenant: str | None) -> GatewayPolicyBinding:
    return GatewayPolicyBinding(id=BID, policy_id=PID, tenant_id=tenant, api_catalog_id=None,
                                gateway_instance_id=None, enabled=True, created_at=datetime.now(UTC))


def persona(role: str = "tenant-admin", tenant: str | None = "tenant-a") -> User:
    return User(id="synthetic", email="person@example.invalid", username="synthetic", roles=[role], tenant_id=tenant)


class SessionSpy:
    def __init__(self, state: SimpleNamespace) -> None:
        self.state = state
        self.reads: list[object] = []
        self.writes: list[str] = []

    async def execute(self, statement: object) -> SimpleNamespace:
        self.reads.append(statement)
        is_policy = statement.column_descriptions[0]["entity"] is GatewayPolicy
        value = self.state.policy if is_policy else self.state.binding
        rows = self.state.policies if is_policy else self.state.bindings
        return SimpleNamespace(scalar_one_or_none=lambda: value, scalars=lambda: SimpleNamespace(all=lambda: rows))

    def add(self, value: object) -> None:
        self.writes.append("add")

    async def flush(self) -> None:
        self.writes.append("flush")

    async def refresh(self, value: object, **kwargs: object) -> None:
        self.writes.append("refresh")
        if value.id is None:
            value.id = uuid4()
            value.created_at = datetime.now(UTC)
            if isinstance(value, GatewayPolicy):
                value.updated_at = value.created_at
                value.bindings = []

    async def commit(self) -> None:
        self.writes.append("commit")

    async def delete(self, value: object) -> None:
        self.writes.append("delete")


@pytest.fixture
def access(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    state = SimpleNamespace(user=persona(), policy=policy("tenant-a"), binding=binding("tenant-a"), events=[])
    state.policies = [policy(t) for t in ["tenant-a", "tenant-b", None]]
    state.bindings = [binding(t) for t in ["tenant-a", "tenant-b", None]]
    state.db = SessionSpy(state)

    async def emit(**kwargs: object) -> None:
        state.events.append(kwargs)

    monkeypatch.setattr(routes, "kafka_service", SimpleNamespace(**{
        "emit_policy_" + event: emit for event in ["created", "updated", "deleted", "binding_created", "binding_deleted"]
    }))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: state.user
    app.dependency_overrides[get_db] = lambda: state.db
    with TestClient(app) as client:
        state.client = client
        yield state


def call(state: SimpleNamespace, op: str, tenant: str | None = "tenant-a"):
    method, path, original, _ = OPS[op]
    body = {**original} if original is not None else None
    if op in ["create", "bind"]:
        body["tenant_id"] = tenant
    params = {"tenant_id": tenant} if op == "list" and tenant is not None else {}
    return state.client.request(method, path, json=body, params=params)


@pytest.mark.parametrize("tenant", [None, "", "   "])
@pytest.mark.parametrize("op", TENANT_OPS)
def test_regression_missing_tenant_stops_before_repository(access: SimpleNamespace, tenant: str | None, op: str) -> None:
    access.user = persona(tenant=tenant)
    assert call(access, op).status_code == 403
    assert access.db.reads == access.db.writes == access.events == []


@pytest.mark.parametrize("op", TENANT_OPS)
def test_regression_own_tenant_operations_remain_allowed(access: SimpleNamespace, op: str) -> None:
    response = call(access, op)
    assert response.status_code == OPS[op][3]
    if op in ["list", "bindings"]:
        assert [item["tenant_id"] for item in response.json()] == ["tenant-a"]
    elif op != "unbind":
        assert response.json()["tenant_id"] == "tenant-a"
    if op in ["create", "update", "bind", "unbind"]:
        assert "commit" in access.db.writes
        assert len(access.events) == 1


@pytest.mark.parametrize("op", ["create", "bind"])
@pytest.mark.parametrize("target", [None, "tenant-b"])
def test_regression_foreign_creation_stops_without_effects(access: SimpleNamespace, op: str, target: str | None) -> None:
    assert call(access, op, target).status_code == 403
    assert access.db.reads == access.db.writes == access.events == []


@pytest.mark.parametrize("op", ["get", "update", "bind", "bindings", "unbind"])
@pytest.mark.parametrize("target", [None, "tenant-b"])
def test_regression_foreign_policy_is_not_found(access: SimpleNamespace, op: str, target: str | None) -> None:
    access.policy.tenant_id = target
    before = access.policy.name
    assert call(access, op).status_code == 404
    assert access.policy.name == before
    assert access.db.writes == access.events == []


@pytest.mark.parametrize("target", [None, "tenant-b"])
def test_regression_unbind_checks_binding_tenant(access: SimpleNamespace, target: str | None) -> None:
    access.binding.tenant_id = target
    assert call(access, "unbind").status_code == 404
    assert access.db.writes == access.events == []


def test_regression_foreign_list_query_cannot_widen_scope(access: SimpleNamespace) -> None:
    response = call(access, "list", "tenant-b")
    assert response.status_code == 200
    assert [item["tenant_id"] for item in response.json()] == ["tenant-a"]
    assert access.db.writes == access.events == []


@pytest.mark.parametrize("target", [None, "tenant-b"])
@pytest.mark.parametrize("op", OPS)
def test_regression_platform_admin_contract_unchanged(access: SimpleNamespace, target: str | None, op: str) -> None:
    access.user = persona("cpi-admin", None)
    access.policy.tenant_id = target
    access.binding.tenant_id = target
    response = call(access, op, target)
    assert response.status_code == OPS[op][3]
    if op in ["list", "bindings"]:
        assert len(response.json()) == 3
    elif op not in ["delete", "unbind"]:
        assert response.json()["tenant_id"] == target


@pytest.mark.parametrize("role", ["viewer", "devops"])
@pytest.mark.parametrize("op", OPS)
def test_regression_non_admin_roles_still_forbidden(access: SimpleNamespace, role: str, op: str) -> None:
    access.user = persona(role)
    assert call(access, op).status_code == 403
    assert access.db.reads == access.db.writes == access.events == []


def test_regression_policy_delete_remains_platform_only(access: SimpleNamespace) -> None:
    assert call(access, "delete").status_code == 403
    assert access.db.reads == access.db.writes == access.events == []
