"""Tests for X-Operator-Key service-to-service auth bypass (ADR-042)."""

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user


@pytest.mark.asyncio
@patch("src.auth.dependencies.settings")
async def test_operator_key_bypass(mock_settings):
    """Valid X-Operator-Key should return stoa-operator with cpi-admin role."""
    mock_settings.gateway_api_keys_list = ["test-operator-key"]
    mock_settings.LOG_DEBUG_AUTH_TOKENS = False
    mock_settings.LOG_DEBUG_AUTH_PAYLOAD = False

    test_app = FastAPI()

    @test_app.get("/test-auth")
    async def endpoint(user: User = Depends(get_current_user)):
        return {"user_id": user.id, "roles": user.roles, "username": user.username}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/test-auth",
            headers={"X-Operator-Key": "test-operator-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "stoa-operator"
    assert "cpi-admin" in data["roles"]
    assert data["username"] == "stoa-operator"


@pytest.mark.asyncio
@patch("src.auth.dependencies.settings")
async def test_invalid_operator_key_rejected(mock_settings):
    """Invalid X-Operator-Key without Bearer token should return 401."""
    mock_settings.gateway_api_keys_list = ["correct-key"]
    mock_settings.LOG_DEBUG_AUTH_TOKENS = False
    mock_settings.LOG_DEBUG_AUTH_PAYLOAD = False

    test_app = FastAPI()

    @test_app.get("/test-auth")
    async def endpoint(user: User = Depends(get_current_user)):
        return {"user_id": user.id}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/test-auth",
            headers={"X-Operator-Key": "wrong-key"},
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
@patch("src.auth.dependencies.settings")
async def test_no_auth_returns_401(mock_settings):
    """Request with no auth headers should return 401."""
    mock_settings.gateway_api_keys_list = []
    mock_settings.LOG_DEBUG_AUTH_TOKENS = False
    mock_settings.LOG_DEBUG_AUTH_PAYLOAD = False

    test_app = FastAPI()

    @test_app.get("/test-auth")
    async def endpoint(user: User = Depends(get_current_user)):
        return {"user_id": user.id}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test-auth")
    assert resp.status_code in (401, 403)
