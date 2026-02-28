"""Tests for federation service — key generation (CAB-1538)."""

import hashlib

from src.services.federation_service import _generate_federation_key


class TestGenerateFederationKey:
    """Tests for the _generate_federation_key pure function."""

    def test_returns_three_values(self):
        plaintext, key_hash, prefix = _generate_federation_key()
        assert isinstance(plaintext, str)
        assert isinstance(key_hash, str)
        assert isinstance(prefix, str)

    def test_prefix_starts_with_stoa_fed(self):
        _, _, prefix = _generate_federation_key()
        assert prefix.startswith("stoa_fed_")

    def test_plaintext_contains_prefix(self):
        plaintext, _, prefix = _generate_federation_key()
        assert plaintext.startswith(prefix + "_")

    def test_hash_is_sha256_hex(self):
        _, key_hash, _ = _generate_federation_key()
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

    def test_hash_matches_plaintext(self):
        plaintext, key_hash, _ = _generate_federation_key()
        expected = hashlib.sha256(plaintext.encode()).hexdigest()
        assert key_hash == expected

    def test_unique_keys_per_call(self):
        results = [_generate_federation_key() for _ in range(10)]
        plaintexts = [r[0] for r in results]
        hashes = [r[1] for r in results]
        assert len(set(plaintexts)) == 10
        assert len(set(hashes)) == 10

    def test_plaintext_length(self):
        """Prefix (stoa_fed_XXXX) + _ + 64 hex chars = substantial length."""
        plaintext, _, _ = _generate_federation_key()
        assert len(plaintext) > 70
