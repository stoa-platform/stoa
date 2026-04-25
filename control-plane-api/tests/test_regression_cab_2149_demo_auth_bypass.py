"""Regression tests for demo/dev auth bypass used by the executable smoke."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.auth import dependencies as auth_deps
from src.auth.dependencies import User, get_current_user
from src.config import Settings


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/protected")
    async def protected(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"id": user.id, "roles": user.roles}

    return TestClient(app)


def test_regression_cab_2149_demo_bypass_requires_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_deps.settings, "STOA_DISABLE_AUTH", False)

    response = _client().post("/protected", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_regression_cab_2149_demo_bypass_requires_demo_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_deps.settings, "STOA_DISABLE_AUTH", True)

    response = _client().post("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_regression_cab_2149_demo_bypass_returns_cpi_admin_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_deps.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(auth_deps.settings, "STOA_DISABLE_AUTH", True)

    response = _client().post("/protected", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 200
    assert response.json() == {"id": "demo-dev-bypass", "roles": ["cpi-admin"]}


def test_regression_cab_2149_demo_bypass_rejected_in_production() -> None:
    with pytest.raises(ValueError) as exc:
        Settings(ENVIRONMENT="production", STOA_DISABLE_AUTH=True)

    assert "STOA_DISABLE_AUTH=true" in str(exc.value)
