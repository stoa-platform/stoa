"""Fingerprint format utilities for RFC 8705 certificate binding.

Supported formats:
- base64url: hLmVMvjnmCm_I4d8_3nw5A (RFC 8705 JWT cnf claim)
- hex: 84b99532f8e79829bf23877cff79f0e4 (lowercase, no separator)
- hex_colons: 84:B9:95:32:F8:E7:98:29:BF:23:87:7C:FF:79:F0:E4 (OpenSSL)

All comparisons normalize to hex lowercase.
"""

import base64
import re
import secrets
from enum import Enum
from typing import Optional


class FingerprintFormat(str, Enum):
    BASE64URL = "base64url"
    HEX = "hex"
    HEX_COLONS = "hex_colons"


_HEX_PATTERN = re.compile(r"^[a-fA-F0-9]+$")


def detect_format(fingerprint: str) -> FingerprintFormat:
    """Auto-detect fingerprint format from string pattern."""
    if not fingerprint or not fingerprint.strip():
        raise ValueError("Empty fingerprint")
    fp = fingerprint.strip()
    if ":" in fp:
        return FingerprintFormat.HEX_COLONS
    if _HEX_PATTERN.match(fp):
        return FingerprintFormat.HEX
    return FingerprintFormat.BASE64URL


def normalize_to_hex(
    fingerprint: str, fmt: Optional[FingerprintFormat] = None
) -> str:
    """Normalize any fingerprint format to lowercase hex (no separators).

    Args:
        fingerprint: The fingerprint string in any supported format.
        fmt: Optional format hint. Auto-detected if None.

    Returns:
        Lowercase hex string without separators.

    Raises:
        ValueError: If fingerprint is empty or invalid.
    """
    if not fingerprint or not fingerprint.strip():
        raise ValueError("Empty fingerprint")

    fp = fingerprint.strip()
    detected = fmt or detect_format(fp)

    if detected == FingerprintFormat.HEX_COLONS:
        return fp.replace(":", "").lower()

    if detected == FingerprintFormat.HEX:
        if not _HEX_PATTERN.match(fp):
            raise ValueError(f"Invalid hex fingerprint: {fp!r}")
        return fp.lower()

    if detected == FingerprintFormat.BASE64URL:
        # Validate base64url charset before decoding
        if not re.match(r"^[A-Za-z0-9\-_]+$", fp):
            raise ValueError(f"Invalid base64url fingerprint: contains illegal characters")
        # base64url uses - and _ instead of + and /
        standard = fp.replace("-", "+").replace("_", "/")
        # Add padding
        pad = 4 - len(standard) % 4
        if pad != 4:
            standard += "=" * pad
        try:
            decoded = base64.b64decode(standard)
        except Exception as e:
            raise ValueError(f"Invalid base64url fingerprint: {e}") from e
        return decoded.hex()

    raise ValueError(f"Unknown format: {detected}")


def hex_to_base64url(hex_fingerprint: str) -> str:
    """Convert hex fingerprint to base64url (for JWT cnf claim).

    Args:
        hex_fingerprint: Hex string (with or without colons).

    Returns:
        base64url string without padding.
    """
    clean = hex_fingerprint.replace(":", "").strip().lower()
    raw = bytes.fromhex(clean)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def fingerprints_match(
    fp1: str,
    fp2: str,
    format1: Optional[FingerprintFormat] = None,
    format2: Optional[FingerprintFormat] = None,
) -> bool:
    """Compare two fingerprints using timing-safe comparison.

    Normalizes both to hex lowercase before comparing.
    Returns False (without raising) on invalid input.
    """
    try:
        n1 = normalize_to_hex(fp1, format1)
        n2 = normalize_to_hex(fp2, format2)
        return secrets.compare_digest(n1, n2)
    except (ValueError, TypeError):
        return False
