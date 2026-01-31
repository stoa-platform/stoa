"""Tests for fingerprint_utils — RFC 8705 format normalization."""

import pytest

from src.services.fingerprint_utils import (
    FingerprintFormat,
    detect_format,
    fingerprints_match,
    hex_to_base64url,
    normalize_to_hex,
)

# Test vectors: same SHA-256 fingerprint in all 3 formats
FP_HEX = "84b99532f8e79829bf23877cff79f0e4"
FP_HEX_UPPER = "84B99532F8E79829BF23877CFF79F0E4"
FP_HEX_COLONS = "84:B9:95:32:F8:E7:98:29:BF:23:87:7C:FF:79:F0:E4"
FP_BASE64URL = "hLmVMvjnmCm_I4d8_3nw5A"


# =============================================================================
# detect_format
# =============================================================================


class TestDetectFormat:
    def test_detect_hex(self):
        assert detect_format(FP_HEX) == FingerprintFormat.HEX

    def test_detect_hex_colons(self):
        assert detect_format(FP_HEX_COLONS) == FingerprintFormat.HEX_COLONS

    def test_detect_base64url(self):
        assert detect_format(FP_BASE64URL) == FingerprintFormat.BASE64URL

    def test_detect_empty_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            detect_format("")

    def test_detect_whitespace_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            detect_format("   ")


# =============================================================================
# normalize_to_hex
# =============================================================================


class TestNormalizeToHex:
    def test_from_hex_lowercase(self):
        assert normalize_to_hex(FP_HEX) == FP_HEX

    def test_from_hex_uppercase(self):
        assert normalize_to_hex(FP_HEX_UPPER) == FP_HEX

    def test_from_hex_colons(self):
        assert normalize_to_hex(FP_HEX_COLONS) == FP_HEX

    def test_from_base64url(self):
        assert normalize_to_hex(FP_BASE64URL) == FP_HEX

    def test_explicit_format_hint(self):
        assert normalize_to_hex(FP_HEX_COLONS, FingerprintFormat.HEX_COLONS) == FP_HEX

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            normalize_to_hex("")

    def test_invalid_base64url_raises(self):
        with pytest.raises(ValueError, match="Invalid base64url"):
            normalize_to_hex("!!!invalid!!!", FingerprintFormat.BASE64URL)


# =============================================================================
# hex_to_base64url
# =============================================================================


class TestHexToBase64url:
    def test_basic(self):
        result = hex_to_base64url(FP_HEX)
        assert result == FP_BASE64URL

    def test_round_trip(self):
        b64 = hex_to_base64url(FP_HEX)
        back = normalize_to_hex(b64, FingerprintFormat.BASE64URL)
        assert back == FP_HEX

    def test_from_colons(self):
        result = hex_to_base64url(FP_HEX_COLONS)
        assert result == FP_BASE64URL


# =============================================================================
# fingerprints_match
# =============================================================================


class TestFingerprintsMatch:
    def test_same_format_match(self):
        assert fingerprints_match(FP_HEX, FP_HEX) is True

    def test_cross_format_hex_base64url(self):
        assert fingerprints_match(FP_HEX, FP_BASE64URL) is True

    def test_cross_format_colons_base64url(self):
        assert fingerprints_match(FP_HEX_COLONS, FP_BASE64URL) is True

    def test_cross_format_all_three(self):
        assert fingerprints_match(
            FP_HEX_COLONS,
            FP_BASE64URL,
            FingerprintFormat.HEX_COLONS,
            FingerprintFormat.BASE64URL,
        ) is True

    def test_different_values_no_match(self):
        assert fingerprints_match(FP_HEX, "abcd1234" * 4) is False

    def test_invalid_input_returns_false(self):
        assert fingerprints_match("", FP_HEX) is False

    def test_none_input_returns_false(self):
        assert fingerprints_match(None, FP_HEX) is False  # type: ignore[arg-type]
