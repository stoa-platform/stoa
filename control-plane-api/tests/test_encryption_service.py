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
