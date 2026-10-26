"""Joint guards through real FastAPI DI/ASGI and an observable SQLite repository.

Fixture routes model common guard compositions.
Only authentication is overridden; guards, dependency resolution and SQL are real.
This does not exercise production routers, their repositories or JWT validation.
"""

import sqlite3
from contextlib import closing

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user
from src.auth.rbac import Permission, normalize_roles, require_permission, require_role, require_tenant_access
from tests.guard_loop import guard_loop as guard_loop

ALLOWED = ["cpi-admin", "tenant-admin"]
# Explicit expectations from the supplied base; never computed by the guard under test.
ACTORS = (
    (("cpi-admin",), True, True, True),
    (("tenant-admin",), True, True, False),
    (("devops",), False, True, False),
    (("viewer",), False, False, False),
    ((), False, False, False),
    (("unknown",), False, False, False),
    (("stoa.security",), False, False, False),
    (("stoa.agent",), False, False, False),
    (("viewer", "tenant-admin"), True, True, False),
    (("unknown", "devops"), False, True, False),
    (("viewer", "cpi-admin"), True, True, True),
    (tuple(normalize_roles(["stoa.admin"])), True, True, True),
)
COMPOSITIONS = (
    "role",
    "restricted-role",
    "permission-tenant",
    "tenant-permission",
    "role-permission-tenant",
    "role-tenant-permission",
)


class SQLiteRepository:
    """Real in-memory SQL operations with a counter at repository entry."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.calls = 0

    def execute(self, operation: str, tenant_id: str) -> list[str]:
        self.calls += 1
        if operation == "read":
            rows = self.db.execute("SELECT value FROM records WHERE tenant_id = ?", (tenant_id,))
            return [row[0] for row in rows]
        self.db.execute("INSERT INTO records VALUES (?, ?)", (tenant_id, "added-marker"))
        return ["added-marker"]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("own_tenant", ["acme", "other", None])
@pytest.mark.parametrize("composition", COMPOSITIONS)
@pytest.mark.parametrize("operation", ["read", "write"])
async def test_joint_guards_no_denied_repository_effect(
    actor: tuple[tuple[str, ...], bool, bool, bool],
    own_tenant: str | None,
    composition: str,
    operation: str,
) -> None:
    roles, role_ok, permission_ok, platform_admin = actor
    user = User(
        id="fixture", email="fixture@example.invalid", username="fixture", roles=list(roles), tenant_id=own_tenant
    )
    original_roles = list(user.roles)
    app = FastAPI()

    async def authenticated_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = authenticated_user
    role_required = "role" in composition
    permission_required = "permission" in composition
    allowed_roles = ["tenant-admin"] if composition == "restricted-role" else ALLOWED
    if composition == "restricted-role":
        role_ok = "tenant-admin" in roles
    user_dependency = require_role(allowed_roles) if role_required else get_current_user
    tenant_ok = platform_admin or own_tenant == "acme"
    expected_detail = None
    if role_required and not role_ok:
        expected_detail = f"Access denied. Required roles: {allowed_roles}"
    elif composition.endswith("tenant-permission") and not tenant_ok:
        expected_detail = "Access denied to this tenant"
    elif permission_required and not permission_ok:
        expected_detail = f"Permission denied: {Permission.APIS_UPDATE} required"
    elif not tenant_ok:
        expected_detail = "Access denied to this tenant"

    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.execute("CREATE TABLE records (tenant_id TEXT, value TEXT)")
        db.executemany("INSERT INTO records VALUES (?, ?)", [("acme", "own-marker"), ("other", "foreign-marker")])
        repo = SQLiteRepository(db)
        statements: list[str] = []
        effects: list[str] = []
        db.set_trace_callback(statements.append)

        async def endpoint(tenant_id: str, user: User = Depends(user_dependency)) -> dict:
            assert user is authenticated_actor
            effects.append(tenant_id)
            return {"items": repo.execute(operation, tenant_id)}

        authenticated_actor = user
        if composition.endswith("tenant-permission"):
            guarded = require_tenant_access(require_permission(Permission.APIS_UPDATE)(endpoint))
        else:
            guarded = require_tenant_access(endpoint)
            if permission_required:
                guarded = require_permission(Permission.APIS_UPDATE)(guarded)
        app.add_api_route("/tenants/{tenant_id}/records", guarded, methods=["POST"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture.invalid") as client:
            response = await client.post("/tenants/acme/records")

        if expected_detail is None:
            assert response.status_code == 200
            expected_items = ["own-marker"] if operation == "read" else ["added-marker"]
            assert response.json() == {"items": expected_items}
            assert repo.calls == 1
            assert effects == ["acme"]
            assert len(statements) == 1
        else:
            assert response.status_code == 403
            assert response.json() == {"detail": expected_detail}
            assert repo.calls == 0
            assert effects == []
            assert statements == []
            assert "own-marker" not in response.text
            assert "added-marker" not in response.text
        assert "foreign-marker" not in response.text
        assert user.roles == original_roles
        assert user.tenant_id == own_tenant
        db.set_trace_callback(None)
        assert db.execute("SELECT value FROM records WHERE tenant_id = 'other'").fetchall() == [("foreign-marker",)]
        expected_count = 3 if operation == "write" and expected_detail is None else 2
        assert db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == expected_count
