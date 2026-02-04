"""Tests for configuration management."""

from __future__ import annotations

from pathlib import Path

from src.config import (
    Credentials,
    StoaConfig,
    clear_credentials,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)


class TestStoaConfig:
    def test_defaults(self):
        cfg = StoaConfig()
        assert cfg.server == "https://api.gostoa.dev"
        assert cfg.realm == "stoa"
        assert cfg.client_id == "stoa-cli"
        assert cfg.tenant_id is None

    def test_token_endpoint(self):
        cfg = StoaConfig(auth_server="https://auth.example.com", realm="myrealm")
        assert cfg.token_endpoint == (
            "https://auth.example.com/realms/myrealm"
            "/protocol/openid-connect/token"
        )

    def test_authorize_endpoint(self):
        cfg = StoaConfig(auth_server="https://auth.example.com", realm="stoa")
        assert "/protocol/openid-connect/auth" in cfg.authorize_endpoint

    def test_userinfo_endpoint(self):
        cfg = StoaConfig()
        assert "/protocol/openid-connect/userinfo" in cfg.userinfo_endpoint


class TestConfigPersistence:
    def test_save_and_load(self, tmp_stoa_dir: Path):
        cfg = StoaConfig(
            server="https://custom.api.dev",
            auth_server="https://custom.auth.dev",
            realm="custom",
            client_id="custom-cli",
            tenant_id="tenant-x",
        )
        save_config(cfg)
        loaded = load_config()
        assert loaded.server == cfg.server
        assert loaded.auth_server == cfg.auth_server
        assert loaded.realm == cfg.realm
        assert loaded.client_id == cfg.client_id
        assert loaded.tenant_id == cfg.tenant_id

    def test_load_missing_file(self, tmp_stoa_dir: Path):
        cfg = load_config()
        assert cfg.server == "https://api.gostoa.dev"

    def test_save_without_tenant(self, tmp_stoa_dir: Path):
        cfg = StoaConfig()
        save_config(cfg)
        loaded = load_config()
        assert loaded.tenant_id is None


class TestCredentialsPersistence:
    def test_save_and_load(self, tmp_stoa_dir: Path):
        creds = Credentials(
            access_token="tok123",
            refresh_token="ref456",
            expires_at=9999999999.0,
            token_type="Bearer",
            claims={"sub": "user1"},
        )
        save_credentials(creds)
        loaded = load_credentials()
        assert loaded.access_token == "tok123"
        assert loaded.refresh_token == "ref456"
        assert loaded.claims["sub"] == "user1"

    def test_credentials_file_permissions(self, tmp_stoa_dir: Path):
        creds = Credentials(access_token="secret")
        save_credentials(creds)
        cred_file = tmp_stoa_dir / "credentials.json"
        mode = oct(cred_file.stat().st_mode)[-3:]
        assert mode == "600"

    def test_clear_credentials(self, tmp_stoa_dir: Path):
        creds = Credentials(access_token="tok")
        save_credentials(creds)
        clear_credentials()
        loaded = load_credentials()
        assert loaded.access_token == ""

    def test_clear_nonexistent(self, tmp_stoa_dir: Path):
        clear_credentials()  # should not raise

    def test_load_missing_file(self, tmp_stoa_dir: Path):
        creds = load_credentials()
        assert creds.access_token == ""
