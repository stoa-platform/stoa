"""Shared test fixtures for STOA CLI tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.config import Credentials, StoaConfig


@pytest.fixture()
def tmp_stoa_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.stoa to a temporary directory."""
    stoa_dir = tmp_path / ".stoa"
    stoa_dir.mkdir()
    monkeypatch.setattr("src.config.STOA_DIR", stoa_dir)
    monkeypatch.setattr("src.config.CONFIG_FILE", stoa_dir / "config.yaml")
    monkeypatch.setattr("src.config.CREDENTIALS_FILE", stoa_dir / "credentials.json")
    return stoa_dir


@pytest.fixture()
def sample_config() -> StoaConfig:
    return StoaConfig(
        server="https://api.test.gostoa.dev",
        auth_server="https://auth.test.gostoa.dev",
        realm="stoa",
        client_id="stoa-cli",
        tenant_id="acme",
    )


@pytest.fixture()
def sample_jwt_payload() -> dict:
    return {
        "sub": "user-123",
        "preferred_username": "john.doe",
        "email": "john@acme.com",
        "tenant_id": "acme",
        "realm_access": {"roles": ["tenant-admin"]},
        "aud": ["stoa-cli"],
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }


def _make_fake_jwt(payload: dict) -> str:
    """Build a fake JWT (header.payload.sig) for testing."""
    import base64

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{body}.fake_signature"


@pytest.fixture()
def fake_jwt(sample_jwt_payload: dict) -> str:
    return _make_fake_jwt(sample_jwt_payload)


@pytest.fixture()
def sample_credentials(fake_jwt: str, sample_jwt_payload: dict) -> Credentials:
    return Credentials(
        access_token=fake_jwt,
        refresh_token="refresh-token-abc",
        expires_at=time.time() + 3600,
        token_type="Bearer",
        claims=sample_jwt_payload,
    )


@pytest.fixture()
def expired_credentials(fake_jwt: str, sample_jwt_payload: dict) -> Credentials:
    return Credentials(
        access_token=fake_jwt,
        refresh_token="refresh-token-abc",
        expires_at=time.time() - 100,
        token_type="Bearer",
        claims=sample_jwt_payload,
    )
