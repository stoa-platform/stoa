"""In-process HTTP checks: real RBAC guards and an observable handler effect.

Only authentication is overridden. These routes exercise FastAPI integration;
they do not claim production-router, database or JWT coverage.
"""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user
from src.auth.rbac import require_permission, require_role
from tests.guard_loop import guard_loop as guard_loop
from tests.permission_cases import ALLOWED_CASES, PERMISSIONS, ROLE_CASES, expected_permission, make_user


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ROLE_CASES)
@pytest.mark.parametrize("allowed", ALLOWED_CASES)
async def test_role_http(roles: tuple[str, ...], allowed: tuple[str, ...]) -> None:
    app = FastAPI()
    actor = make_user(roles)
    effects: list[str] = []

    async def authenticated_user() -> User:
        return actor

    app.dependency_overrides[get_current_user] = authenticated_user

    @app.post("/guarded-role")
    async def operation(user: User = Depends(require_role(list(allowed)))) -> dict[str, str]:
        effects.append(user.id)
        return {"actor": user.id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://rbac.invalid") as client:
        response = await client.post("/guarded-role")
    if set(roles).intersection(allowed):
        assert response.status_code == 200
        assert response.json() == {"actor": actor.id}
        assert effects == [actor.id]
    else:
        assert response.status_code == 403
        assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ROLE_CASES)
@pytest.mark.parametrize("permission", (*PERMISSIONS, "fixture:undeclared"))
async def test_permission_http(roles: tuple[str, ...], permission: str) -> None:
    app = FastAPI()
    actor = make_user(roles)
    effects: list[str] = []

    async def authenticated_user() -> User:
        return actor

    app.dependency_overrides[get_current_user] = authenticated_user

    @app.post("/guarded-permission")
    @require_permission(permission)
    async def operation(user: User = Depends(get_current_user)) -> dict[str, str]:
        effects.append(user.id)
        return {"actor": user.id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://rbac.invalid") as client:
        response = await client.post("/guarded-permission")
    if expected_permission(roles, permission):
        assert response.status_code == 200
        assert response.json() == {"actor": actor.id}
        assert effects == [actor.id]
    else:
        assert response.status_code == 403
        assert effects == []
