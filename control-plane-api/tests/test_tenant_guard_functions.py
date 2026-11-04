"""Tenant boundary contract; no changes to role or permission checks."""

import unittest

import pytest
from fastapi import HTTPException

from src.auth.dependencies import User
from src.auth.rbac import decide_tenant_access, ensure_tenant, normalize_roles, require_tenant_access
from tests.guard_loop import guard_loop as guard_loop


@pytest.mark.parametrize("role", ["cpi-admin", "tenant-admin", "devops", "viewer"])
@pytest.mark.parametrize("tenant", ["acme", None, "", " "])
@pytest.mark.parametrize(
    ("mode", "target", "member_result", "admin_result"),
    [
        ("resource", "acme", "acme", "acme"),
        ("resource", "other", 403, "other"),
        ("resource", None, 403, 403),
        ("resource", "", 403, 403),
        ("resource", " ", 403, 403),
        ("filter", "other", "acme", "other"),
        ("filter", " acme ", "acme", "acme"),
        ("filter", None, "acme", 403),
        ("global", None, 403, None),
        ("global", "acme", 403, 403),
        ("unsupported", None, 403, 403),
    ],
)
def test_tenant_decision_modes(role, tenant, mode, target, member_result, admin_result):
    user = User(id="fixture", email="fixture@example.invalid", username="fixture", roles=[role], tenant_id=tenant)
    expected = admin_result if role == "cpi-admin" else member_result if tenant and tenant.strip() else 403
    if expected == 403:
        with pytest.raises(HTTPException) as caught:
            decide_tenant_access(user, target, mode=mode)
        assert caught.value.status_code == 403
    else:
        assert decide_tenant_access(user, target, mode=mode) == expected


@pytest.mark.parametrize("target", [None, "", " "])
async def test_resource_facades_require_admin_target(target):
    user = User(id="fixture", email="fixture@example.invalid", username="fixture", roles=["cpi-admin"])

    @require_tenant_access
    async def endpoint(**kwargs):
        pytest.fail("A missing target must not reach the endpoint")

    for guard in (endpoint, ensure_tenant):
        with pytest.raises(HTTPException) as caught:
            await guard(tenant_id=target, user=user)
        assert caught.value.status_code == 403


class TestTenantAccessContract(unittest.IsolatedAsyncioTestCase):
    async def test_tenant_matrix(self) -> None:
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
                    user = User(
                        id="fixture",
                        email="fixture@example.invalid",
                        username="fixture",
                        roles=roles,
                        tenant_id=own_tenant,
                    )
                    calls = []

                    @require_tenant_access
                    async def endpoint(
                        *, tenant_id: str, user: User, marker: object, recorded_calls: list = calls
                    ) -> object:
                        recorded_calls.append((tenant_id, user, marker))
                        return marker

                    marker = object()
                    if "cpi-admin" in roles or own_tenant == "acme":
                        result = await endpoint(tenant_id="acme", user=user, marker=marker)
                        self.assertIs(result, marker)
                        self.assertEqual(len(calls), 1)
                        self.assertEqual(calls[0][0], "acme")
                        self.assertIs(calls[0][1], user)
                        self.assertIs(calls[0][2], marker)
                    else:
                        with self.assertRaises(HTTPException) as caught:
                            await endpoint(tenant_id="acme", user=user, marker=marker)
                        self.assertEqual(caught.exception.status_code, 403)
                        self.assertEqual(caught.exception.detail, "Access denied to this tenant")
                        self.assertEqual(calls, [])
                    self.assertEqual(user.roles, roles)
                    self.assertEqual(user.tenant_id, own_tenant)


if __name__ == "__main__":
    unittest.main()
