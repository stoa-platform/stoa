"""Unit tests for APIKeyService — api_key.py (CAB-1437 Phase 2)

Tests key generation, hashing, format validation, and masking.
"""

from src.services.api_key import APIKeyService


class TestGenerateKey:
    def test_default_prefix(self):
        full_key, _key_hash, _display_prefix = APIKeyService.generate_key()
        assert full_key.startswith("stoa_sk_")
        assert len(full_key) == len("stoa_sk_") + 32

    def test_custom_prefix(self):
        full_key, _, _ = APIKeyService.generate_key(prefix="stoa_mcp_")
        assert full_key.startswith("stoa_mcp_")

    def test_returns_hash(self):
        _, key_hash, _ = APIKeyService.generate_key()
        assert len(key_hash) == 64  # SHA-256 hex digest

    def test_returns_display_prefix(self):
        full_key, _, display_prefix = APIKeyService.generate_key()
        assert display_prefix == full_key[:12]

    def test_unique_keys(self):
        key1, _, _ = APIKeyService.generate_key()
        key2, _, _ = APIKeyService.generate_key()
        assert key1 != key2

    def test_hash_matches_key(self):
        full_key, key_hash, _ = APIKeyService.generate_key()
        assert APIKeyService.hash_key(full_key) == key_hash


class TestHashKey:
    def test_deterministic(self):
        h1 = APIKeyService.hash_key("stoa_sk_abcdef1234567890abcdef1234567890")
        h2 = APIKeyService.hash_key("stoa_sk_abcdef1234567890abcdef1234567890")
        assert h1 == h2

    def test_different_keys_different_hashes(self):
        h1 = APIKeyService.hash_key("stoa_sk_aaaa")
        h2 = APIKeyService.hash_key("stoa_sk_bbbb")
        assert h1 != h2


class TestValidateFormat:
    def test_valid_key(self):
        full_key, _, _ = APIKeyService.generate_key()
        assert APIKeyService.validate_format(full_key) is True

    def test_empty_string(self):
        assert APIKeyService.validate_format("") is False

    def test_wrong_prefix(self):
        assert APIKeyService.validate_format("wrong_abcdef1234567890abcdef1234567890") is False

    def test_too_short(self):
        assert APIKeyService.validate_format("stoa_sk_abc") is False

    def test_too_long(self):
        assert APIKeyService.validate_format("stoa_sk_" + "a" * 33) is False

    def test_non_hex_chars(self):
        assert APIKeyService.validate_format("stoa_sk_" + "g" * 32) is False

    def test_exact_length_valid_hex(self):
        assert APIKeyService.validate_format("stoa_sk_" + "0" * 32) is True


class TestMaskKey:
    def test_normal_key(self):
        masked = APIKeyService.mask_key("stoa_sk_abcdef1234567890abcdef1234567890")
        assert masked == "stoa_sk_...7890"

    def test_short_key(self):
        assert APIKeyService.mask_key("short") == "***"

    def test_exactly_12_chars(self):
        masked = APIKeyService.mask_key("123456789012")
        assert masked.startswith("12345678")
        assert masked.endswith("9012")
