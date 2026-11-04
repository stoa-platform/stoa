"""Real ASGI requests and SQLite reads behind the real tenant decorator.

This small fixture route validates the authorization boundary, not a production
router or the project's repositories. Authentication is overridden only for
identified matrix users; the anonymous case uses the real get_current_user.
"""

import sqlite3
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth import dependencies
from src.auth.dependencies import User, get_current_user
from src.auth.rbac import decide_tenant_access, normalize_roles, require_tenant_access, resolve_effective_tenant
from tests.guard_loop import guard_loop as guard_loop


class TestTenantAccessHTTP(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE tenant_data (tenant_id TEXT, value TEXT)")
        self.db.executemany(
            "INSERT INTO tenant_data VALUES (?, ?)",
            [("acme", "private-acme-marker"), ("other", "private-other-marker")],
        )
        self.reads = []
        self.db.set_trace_callback(self.reads.append)
        self.endpoint_calls = []

    def make_app(self, user: User | None = None) -> FastAPI:
        app = FastAPI()
        if user is not None:

            async def identified_user() -> User:
                return user

            app.dependency_overrides[get_current_user] = identified_user

        @app.get("/tenants/{tenant_id}/data")
        @require_tenant_access
        async def endpoint(tenant_id: str, user: User = Depends(get_current_user)) -> dict:
            self.endpoint_calls.append(tenant_id)
            rows = self.db.execute("SELECT value FROM tenant_data WHERE tenant_id = ?", (tenant_id,))
            return {"items": [row[0] for row in rows]}

        @app.get("/data")
        async def filtered(tenant_id: str | None = None, user: User = Depends(get_current_user)) -> dict:
            tenant = resolve_effective_tenant(user, tenant_id)
            rows = self.db.execute("SELECT value FROM tenant_data WHERE ? IS NULL OR tenant_id = ?", (tenant, tenant))
            return {"items": [row[0] for row in rows]}

        @app.get("/global")
        async def global_data(user: User = Depends(get_current_user)) -> dict:
            decide_tenant_access(user, mode="global")
            return {"items": [row[0] for row in self.db.execute("SELECT value FROM tenant_data")]}

        return app

    async def test_http_matrix_no_denied_reads(self) -> None:
        role_sets = [
            ["cpi-admin"],
            ["tenant-admin"],
            ["devops"],
            ["viewer"],
            [],
            ["unknown"],
            ["viewer", "cpi-admin"],
            normalize_roles(["stoa.admin"]),
        ]
        for roles in role_sets:
            for own_tenant in ["acme", "other", None]:
                with self.subTest(roles=roles, own_tenant=own_tenant):
                    self.reads.clear()
                    self.endpoint_calls.clear()
                    user = User(
                        id="fixture",
                        email="fixture@example.invalid",
                        username="fixture",
                        roles=roles,
                        tenant_id=own_tenant,
                    )
                    transport = ASGITransport(app=self.make_app(user))
                    async with AsyncClient(transport=transport, base_url="http://fixture.invalid") as client:
                        response = await client.get("/tenants/acme/data", headers={"X-Tenant-ID": "other"})
                    if "cpi-admin" in roles or own_tenant == "acme":
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {"items": ["private-acme-marker"]})
                        self.assertEqual(self.endpoint_calls, ["acme"])
                        self.assertEqual(len(self.reads), 1)
                    else:
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(response.json(), {"detail": "Access denied to this tenant"})
                        self.assertEqual(self.endpoint_calls, [])
                        self.assertEqual(self.reads, [])
                    self.assertNotIn("private-other-marker", response.text)
                    if response.status_code != 200:
                        self.assertNotIn("private-acme-marker", response.text)

    async def test_filter_and_global_modes(self) -> None:
        for role in ["cpi-admin", "tenant-admin", "devops", "viewer"]:
            for tenant in ["acme", None]:
                user = User(
                    id="fixture", email="fixture@example.invalid", username="fixture", roles=[role], tenant_id=tenant
                )
                for path in ["/data", "/data?tenant_id=other", "/global"]:
                    with self.subTest(role=role, tenant=tenant, path=path):
                        self.reads.clear()
                        async with AsyncClient(
                            transport=ASGITransport(app=self.make_app(user)), base_url="http://fixture.invalid"
                        ) as client:
                            response = await client.get(path, headers={"X-Tenant-ID": "other"})
                        if role != "cpi-admin" and (tenant is None or path == "/global"):
                            self.assertEqual(response.status_code, 403)
                            self.assertEqual(self.reads, [])
                        else:
                            self.assertEqual(response.status_code, 200)
                            expected = ["private-acme-marker"]
                            if role == "cpi-admin":
                                expected = (
                                    ["private-other-marker"] if "?" in path else [*expected, "private-other-marker"]
                                )
                            self.assertEqual(response.json(), {"items": expected})
                            self.assertEqual(len(self.reads), 1)

    async def test_anonymous_current_auth_contract(self) -> None:
        # The current authentication contract is 401; tenant authorization is 403.
        # Changing this to 403 needs an explicit contract decision.
        with patch.object(dependencies.settings, "STOA_DISABLE_AUTH", False):
            transport = ASGITransport(app=self.make_app())
            async with AsyncClient(transport=transport, base_url="http://fixture.invalid") as client:
                response = await client.get("/tenants/acme/data", headers={"X-Tenant-ID": "acme"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Not authenticated"})
        self.assertEqual(self.endpoint_calls, [])
        self.assertEqual(self.reads, [])
        self.assertNotIn("private-acme-marker", response.text)
        self.assertNotIn("private-other-marker", response.text)


if __name__ == "__main__":
    unittest.main()
