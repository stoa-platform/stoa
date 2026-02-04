"""Configuration management for STOA CLI.

Stores server URL and credentials in ~/.stoa/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STOA_DIR = Path.home() / ".stoa"
CONFIG_FILE = STOA_DIR / "config.yaml"
CREDENTIALS_FILE = STOA_DIR / "credentials.json"

DEFAULT_SERVER = "https://api.gostoa.dev"
DEFAULT_AUTH_SERVER = "https://auth.gostoa.dev"
DEFAULT_REALM = "stoa"
DEFAULT_CLIENT_ID = "stoa-cli"


@dataclass
class StoaConfig:
    server: str = DEFAULT_SERVER
    auth_server: str = DEFAULT_AUTH_SERVER
    realm: str = DEFAULT_REALM
    client_id: str = DEFAULT_CLIENT_ID
    tenant_id: str | None = None

    @property
    def token_endpoint(self) -> str:
        return (
            f"{self.auth_server}/realms/{self.realm}"
            f"/protocol/openid-connect/token"
        )

    @property
    def authorize_endpoint(self) -> str:
        return (
            f"{self.auth_server}/realms/{self.realm}"
            f"/protocol/openid-connect/auth"
        )

    @property
    def userinfo_endpoint(self) -> str:
        return (
            f"{self.auth_server}/realms/{self.realm}"
            f"/protocol/openid-connect/userinfo"
        )


@dataclass
class Credentials:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    token_type: str = "Bearer"
    claims: dict[str, object] = field(default_factory=dict)


def ensure_stoa_dir() -> Path:
    STOA_DIR.mkdir(parents=True, exist_ok=True)
    return STOA_DIR


def load_config() -> StoaConfig:
    if not CONFIG_FILE.exists():
        return StoaConfig()
    with CONFIG_FILE.open() as f:
        data = yaml.safe_load(f) or {}
    return StoaConfig(
        server=data.get("server", DEFAULT_SERVER),
        auth_server=data.get("auth_server", DEFAULT_AUTH_SERVER),
        realm=data.get("realm", DEFAULT_REALM),
        client_id=data.get("client_id", DEFAULT_CLIENT_ID),
        tenant_id=data.get("tenant_id"),
    )


def save_config(cfg: StoaConfig) -> None:
    ensure_stoa_dir()
    data = {
        "server": cfg.server,
        "auth_server": cfg.auth_server,
        "realm": cfg.realm,
        "client_id": cfg.client_id,
    }
    if cfg.tenant_id:
        data["tenant_id"] = cfg.tenant_id
    with CONFIG_FILE.open("w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def load_credentials() -> Credentials:
    if not CREDENTIALS_FILE.exists():
        return Credentials()
    with CREDENTIALS_FILE.open() as f:
        data = json.load(f)
    return Credentials(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_at=data.get("expires_at", 0.0),
        token_type=data.get("token_type", "Bearer"),
        claims=data.get("claims", {}),
    )


def save_credentials(creds: Credentials) -> None:
    ensure_stoa_dir()
    data = {
        "access_token": creds.access_token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expires_at,
        "token_type": creds.token_type,
        "claims": creds.claims,
    }
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    CREDENTIALS_FILE.chmod(0o600)


def clear_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
