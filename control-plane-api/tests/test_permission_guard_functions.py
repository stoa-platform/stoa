"""Direct RBAC checks against main's frozen role/permission matrix."""

import pytest
from fastapi import HTTPException

from src.auth.dependencies import User
from src.auth.rbac import get_user_permissions, require_permission, require_role
from tests.guard_loop import guard_loop as guard_loop
from tests.permission_cases import (
    ALLOWED_CASES,
    EXPECTED,
    PERMISSIONS,
    ROLE_CASES,
    expected_permission,
    make_user,
)


@pytest.mark.parametrize("roles", ROLE_CASES)
def test_permission_union(roles: tuple[str, ...]) -> None:
    expected = set().union(*(EXPECTED.get(role, set()) for role in roles))
    assert set(get_user_permissions(list(roles))) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ROLE_CASES)
@pytest.mark.parametrize("allowed", ALLOWED_CASES)
async def test_role_function(roles: tuple[str, ...], allowed: tuple[str, ...]) -> None:
    user = make_user(roles)
    checker = require_role(list(allowed))
    if set(roles).intersection(allowed):
        assert await checker(user=user) is user
    else:
        with pytest.raises(HTTPException) as exc:
            await checker(user=user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ROLE_CASES)
@pytest.mark.parametrize("permission", (*PERMISSIONS, "fixture:undeclared"))
async def test_permission_function(roles: tuple[str, ...], permission: str) -> None:
    user = make_user(roles)
    calls: list[tuple[str, User]] = []

    @require_permission(permission)
    async def operation(marker: str, user: User) -> str:
        calls.append((marker, user))
        return marker

    if expected_permission(roles, permission):
        assert await operation("effect", user=user) == "effect"
        assert calls == [("effect", user)]
    else:
        with pytest.raises(HTTPException) as exc:
            await operation("effect", user=user)
        assert exc.value.status_code == 403
        assert calls == []
