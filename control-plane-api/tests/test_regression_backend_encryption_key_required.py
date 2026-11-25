"""Production without a private BACKEND_ENCRYPTION_KEY: warn by default, refuse when required.

The key counts as missing when unset or set to the public development key.
The default keeps the current behaviour (error log, development key) so a
deployment without the secret can still read what it stored. Setting
BACKEND_ENCRYPTION_KEY_REQUIRED=true turns the same condition into a startup
failure, and also refuses a key that is not a valid Fernet key.
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


@pytest.fixture
def production_with_public_dev_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", enc_mod._DEV_FERNET_KEY.decode())


@pytest.mark.parametrize("padding", ["", " ", "\n"])
def test_public_dev_key_counts_as_missing(production_with_public_dev_key, monkeypatch, padding):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", enc_mod._DEV_FERNET_KEY.decode() + padding)
    assert enc_mod._key_missing_in_production() is True


def test_public_dev_key_comparison_uses_compare_digest(monkeypatch):
    calls = []
    real = enc_mod.hmac.compare_digest

    def spy(a, b):
        calls.append(True)
        return real(a, b)

    monkeypatch.setattr(enc_mod.hmac, "compare_digest", spy)
    assert enc_mod._is_public_dev_key(Fernet.generate_key()) is False
    assert calls


def test_public_dev_key_warns_in_default_mode(production_with_public_dev_key, monkeypatch, caplog):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", False)
    with caplog.at_level(logging.ERROR, logger=enc_mod.__name__):
        enc_mod.ensure_backend_encryption_key()
        token = enc_mod.encrypt_auth_config({"k": "v"})
    assert enc_mod.decrypt_auth_config(token) == {"k": "v"}
    assert sum(MESSAGE in r.getMessage() for r in caplog.records) == 2


def test_public_dev_key_refused_when_required(production_with_public_dev_key, monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with pytest.raises(enc_mod.BackendEncryptionKeyMissingError):
        enc_mod.ensure_backend_encryption_key()
    with pytest.raises(enc_mod.BackendEncryptionKeyMissingError):
        enc_mod.encrypt_auth_config({"k": "v"})
    assert enc_mod._fernet is None


def test_public_dev_key_allowed_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "dev")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", enc_mod._DEV_FERNET_KEY.decode())
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    enc_mod.ensure_backend_encryption_key()
    assert enc_mod.decrypt_auth_config(enc_mod.encrypt_auth_config({"k": "v"})) == {"k": "v"}


MALFORMED = ["synthetic-not-a-fernet-key", "c2hvcnQ=", "!!!!"]


@pytest.mark.parametrize("environment", ["production", "dev"])
@pytest.mark.parametrize("malformed", MALFORMED)
def test_malformed_key_refused_at_startup_when_required(monkeypatch, environment, malformed):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", malformed)
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with pytest.raises(enc_mod.BackendEncryptionKeyInvalidError) as excinfo:
        enc_mod.ensure_backend_encryption_key()
    assert malformed not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_malformed_key_not_checked_at_startup_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", MALFORMED[0])
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", False)
    enc_mod.ensure_backend_encryption_key()


@pytest.mark.asyncio
async def test_lifespan_stops_on_malformed_key_when_required(monkeypatch):
    from src import main

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY", MALFORMED[0])
    monkeypatch.setattr(settings, "BACKEND_ENCRYPTION_KEY_REQUIRED", True)
    with pytest.raises(enc_mod.BackendEncryptionKeyInvalidError):
        async with main.lifespan(main.app):
            pass
