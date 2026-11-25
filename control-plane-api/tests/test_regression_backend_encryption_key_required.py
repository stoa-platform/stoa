"""Production without BACKEND_ENCRYPTION_KEY: warn by default, refuse when required.

The default keeps the current behaviour (error log, development key) so a
deployment without the secret can still read what it stored. Setting
BACKEND_ENCRYPTION_KEY_REQUIRED=true turns the same condition into a startup
failure.
"""

import logging

import pytest
from cryptography.fernet import Fernet

import src.services.encryption_service as enc_mod
from src.config import settings

MESSAGE = "BACKEND_ENCRYPTION_KEY is not set"


@pytest.fixture(autouse=True)
def _reset_fernet():
    enc_mod._fernet = None
    yield
    enc_mod._fernet = None


@pytest.fixture
def production_without_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", "")


def test_required_is_off_by_default():
    assert settings.BACKEND_ENCRYPTION_KEY_REQUIRED is False


def test_default_mode_warns_and_keeps_running(production_without_key, monkeypatch, caplog):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", False)
    with caplog.at_level(logging.ERROR, logger=enc_mod.__name__):
        enc_mod.ensure_backend_encryption_key()
        token = enc_mod.encrypt_auth_config({"k": "v"})
    assert enc_mod.decrypt_auth_config(token) == {"k": "v"}
    assert sum(MESSAGE in r.getMessage() for r in caplog.records) == 2


def test_required_mode_refuses_startup(production_without_key, monkeypatch, caplog):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with (
        caplog.at_level(logging.ERROR, logger=enc_mod.__name__),
        pytest.raises(enc_mod.BackendEncryptionKeyMissingError),
    ):
        enc_mod.ensure_backend_encryption_key()
    assert any(MESSAGE in r.getMessage() for r in caplog.records)


def test_required_mode_never_uses_dev_key(production_without_key, monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with pytest.raises(enc_mod.BackendEncryptionKeyMissingError):
        enc_mod.encrypt_auth_config({"k": "v"})
    assert enc_mod._fernet is None


@pytest.mark.parametrize("required", [False, True])
def test_key_present_passes_in_both_modes(monkeypatch, required, caplog):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", required)
    with caplog.at_level(logging.ERROR, logger=enc_mod.__name__):
        enc_mod.ensure_backend_encryption_key()
        token = enc_mod.encrypt_auth_config({"k": "v"})
    assert enc_mod.decrypt_auth_config(token) == {"k": "v"}
    assert not any(MESSAGE in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("required", [False, True])
def test_outside_production_keeps_dev_key(monkeypatch, required):
    monkeypatch.setattr(settings, "ENVIRONMENT", "dev")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", required)
    enc_mod.ensure_backend_encryption_key()
    assert enc_mod.decrypt_auth_config(enc_mod.encrypt_auth_config({"k": "v"})) == {"k": "v"}


def test_setting_reads_environment(monkeypatch):
    from src.config import Settings

    monkeypatch.setenv("BACKEND_ENCRYPTION_KEY_REQUIRED", "true")
    assert Settings().BACKEND_ENCRYPTION_KEY_REQUIRED is True


@pytest.mark.asyncio
async def test_lifespan_stops_when_required(production_without_key, monkeypatch):
    from src import main

    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with pytest.raises(enc_mod.BackendEncryptionKeyMissingError):
        async with main.lifespan(main.app):
            pass
