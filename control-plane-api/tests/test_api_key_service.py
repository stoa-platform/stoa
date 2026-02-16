"""Tests for API Key service — pure functions, zero mocks."""

from src.services.api_key import APIKeyService


class TestGenerateKey:
    def test_returns_tuple_of_three(self):
        full_key, key_hash, prefix = APIKeyService.generate_key()
        assert isinstance(full_key, str)
        assert isinstance(key_hash, str)
        assert isinstance(prefix, str)

    def test_default_prefix(self):
        full_key, _, _ = APIKeyService.generate_key()
        assert full_key.startswith("stoa_sk_")

    def test_custom_prefix(self):
        full_key, _, _ = APIKeyService.generate_key(prefix="stoa_mcp_")
        assert full_key.startswith("stoa_mcp_")

    def test_key_length(self):
        full_key, _, _ = APIKeyService.generate_key()
        expected = len("stoa_sk_") + 32
        assert len(full_key) == expected

    def test_display_prefix_is_first_12(self):
        full_key, _, prefix = APIKeyService.generate_key()
        assert prefix == full_key[:12]

    def test_uniqueness(self):
        keys = {APIKeyService.generate_key()[0] for _ in range(10)}
        assert len(keys) == 10


class TestHashKey:
    def test_deterministic(self):
        h1 = APIKeyService.hash_key("stoa_sk_abc123")
        h2 = APIKeyService.hash_key("stoa_sk_abc123")
        assert h1 == h2

    def test_hex_format(self):
        h = APIKeyService.hash_key("test")
        assert len(h) == 64  # SHA-256 hex
        int(h, 16)  # valid hex


class TestValidateFormat:
    def test_valid_key(self):
        full_key, _, _ = APIKeyService.generate_key()
        assert APIKeyService.validate_format(full_key) is True

    def test_wrong_prefix(self):
        assert APIKeyService.validate_format("wrong_sk_" + "a" * 32) is False

    def test_wrong_length(self):
        assert APIKeyService.validate_format("stoa_sk_short") is False

    def test_empty_string(self):
        assert APIKeyService.validate_format("") is False

    def test_non_hex_chars(self):
        assert APIKeyService.validate_format("stoa_sk_" + "z" * 32) is False


class TestMaskKey:
    def test_normal_key(self):
        masked = APIKeyService.mask_key("stoa_sk_abcdef1234567890abcdef1234567890")
        assert masked.startswith("stoa_sk_")
        assert masked.endswith("7890")
        assert "..." in masked

    def test_short_key(self):
        assert APIKeyService.mask_key("short") == "***"
