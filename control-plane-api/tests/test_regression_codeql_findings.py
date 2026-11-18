"""Regression tests for CodeQL Python findings in control-plane-api.

- py/weak-sensitive-data-hashing (alert 1543): the dev Fernet key is a constant,
  and its use with ENVIRONMENT=production is reported.
- py/insecure-protocol (alert 1545): the gateway TLS probe refuses TLS 1.0/1.1.
"""

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import src.services.encryption_service as enc_mod
from src.services.diagnostic_service import DiagnosticService


class TestRegressionDevKeyFallback:
    """CodeQL py/weak-sensitive-data-hashing (alert 1543): the dev key is a constant, its use in production is logged."""

    def setup_method(self):
        enc_mod._fernet = None

    def teardown_method(self):
        enc_mod._fernet = None

    def test_regression_production_without_key_is_reported(self, monkeypatch, caplog):
        monkeypatch.setattr(enc_mod.settings, "BACKEND_ENCRYPTION_KEY", "")
        monkeypatch.setattr(enc_mod.settings, "ENVIRONMENT", "production")
        with caplog.at_level("ERROR", logger=enc_mod.logger.name):
            enc_mod.encrypt_auth_config({"k": "v"})
        assert "BACKEND_ENCRYPTION_KEY is not set" in caplog.text

    def test_configured_key_is_used(self, monkeypatch):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setattr(enc_mod.settings, "BACKEND_ENCRYPTION_KEY", key)
        token = enc_mod.encrypt_auth_config({"k": "v"})
        assert Fernet(key.encode()).decrypt(token.encode()) == b'{"k": "v"}'

    def test_dev_key_still_reads_data_written_by_the_runtime_derivation(self, monkeypatch):
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        legacy = Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(b"stoa-dev-encryption-key-not-for-production").digest())
        )
        token = legacy.encrypt(b'{"k": "v"}').decode()
        monkeypatch.setattr(enc_mod.settings, "BACKEND_ENCRYPTION_KEY", "")
        monkeypatch.setattr(enc_mod.settings, "ENVIRONMENT", "dev")
        assert enc_mod.decrypt_auth_config(token) == {"k": "v"}


async def test_regression_tls_stage_refuses_tls_below_1_2() -> None:
    """CodeQL py/insecure-protocol (alert 1545): the TLS probe must not allow TLS 1.0/1.1."""
    mock_gw = MagicMock()
    mock_gw.base_url = "https://127.0.0.1:8443"
    svc = DiagnosticService(AsyncMock())
    contexts: list[ssl.SSLContext] = []
    real_factory = ssl.create_default_context

    def capture_context(*args: object, **kwargs: object) -> ssl.SSLContext:
        ctx = real_factory(*args, **kwargs)
        ctx.wrap_socket = MagicMock()  # type: ignore[method-assign]
        contexts.append(ctx)
        return ctx

    with (
        patch.object(svc, "_get_gateway", return_value=mock_gw),
        patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
        patch("src.services.diagnostic_service.socket.create_connection", return_value=MagicMock()),
        patch("src.services.diagnostic_service.ssl.create_default_context", side_effect=capture_context),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200))),
    ):
        result = await svc.check_connectivity("t1", "gw1")

    assert any(stage.name == "tls" and stage.status == "ok" for stage in result.stages)
    assert contexts and all(ctx.minimum_version == ssl.TLSVersion.TLSv1_2 for ctx in contexts)
