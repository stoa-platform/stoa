"""Tests for encryption service — Fernet round-trip, no network."""

import src.services.encryption_service as enc_mod


class TestEncryptDecryptRoundTrip:
    def setup_method(self):
        # Reset singleton to force re-derivation
        enc_mod._fernet = None

    def test_round_trip(self):
        original = {"api_key": "sk-12345", "auth_type": "bearer"}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_encrypted_is_string(self):
        encrypted = enc_mod.encrypt_auth_config({"key": "val"})
        assert isinstance(encrypted, str)

    def test_different_inputs_different_ciphertexts(self):
        e1 = enc_mod.encrypt_auth_config({"a": 1})
        e2 = enc_mod.encrypt_auth_config({"b": 2})
        assert e1 != e2

    def test_decrypt_with_wrong_key_raises(self):
        # Encrypt with current key
        encrypted = enc_mod.encrypt_auth_config({"secret": "data"})

        # Reset and create a different key
        enc_mod._fernet = None
        from cryptography.fernet import Fernet

        enc_mod._fernet = Fernet(Fernet.generate_key())

        try:
            enc_mod.decrypt_auth_config(encrypted)
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "decrypt" in str(e).lower()
        finally:
            # Reset for other tests
            enc_mod._fernet = None

    def test_nested_dict(self):
        original = {"oauth": {"client_id": "abc", "client_secret": "xyz"}, "scopes": ["read", "write"]}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_empty_dict(self):
        original = {}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_unicode_values(self):
        original = {"key": "clé-secrète-日本語", "note": "émojis: 🔑🔐"}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_same_input_different_ciphertexts(self):
        """Fernet uses a random IV, so same plaintext → different ciphertext each time."""
        data = {"secret": "fixed-value"}
        e1 = enc_mod.encrypt_auth_config(data)
        e2 = enc_mod.encrypt_auth_config(data)
        assert e1 != e2
        assert enc_mod.decrypt_auth_config(e1) == enc_mod.decrypt_auth_config(e2)


class TestEdgeCases:
    def setup_method(self):
        enc_mod._fernet = None

    def test_large_payload_round_trip(self):
        """Large dict with many keys survives encryption round-trip."""
        original = {f"key_{i}": f"value_{i}" * 50 for i in range(100)}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_list_values_in_dict(self):
        """Dict containing list values round-trips correctly."""
        original = {"scopes": ["read", "write", "admin"], "ports": [8080, 443]}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original

    def test_decrypt_corrupted_ciphertext_raises(self):
        """Corrupted ciphertext raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="decrypt"):
            enc_mod.decrypt_auth_config("not-valid-fernet-token")

    def test_decrypt_truncated_ciphertext_raises(self):
        """Truncated ciphertext raises ValueError."""
        import pytest

        encrypted = enc_mod.encrypt_auth_config({"key": "val"})
        truncated = encrypted[:10]
        with pytest.raises(ValueError, match="decrypt"):
            enc_mod.decrypt_auth_config(truncated)

    def test_singleton_reuse(self):
        """_get_fernet returns the same Fernet instance on repeated calls."""
        f1 = enc_mod._get_fernet()
        f2 = enc_mod._get_fernet()
        assert f1 is f2

    def test_deeply_nested_dict(self):
        """Deeply nested structure survives round-trip."""
        original = {"l1": {"l2": {"l3": {"l4": {"secret": "deep"}}}}}
        encrypted = enc_mod.encrypt_auth_config(original)
        decrypted = enc_mod.decrypt_auth_config(encrypted)
        assert decrypted == original


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
