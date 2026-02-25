"""Tests for sender-constrained token validation (CAB-438).

Covers RFC 8705 (mTLS) and RFC 9449 (DPoP) validation paths.
"""

import base64
import hashlib
import time
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from jose import jwt as jose_jwt

from src.auth.sender_constrained import (
    SenderConstrainedResult,
    _compute_ath,
    _compute_jwk_thumbprint,
    _extract_client_cert_fingerprint,
    _jti_cache,
    _validate_dpop_binding,
    _validate_mtls_binding,
    validate_sender_constrained_token,
)


@pytest.fixture(autouse=True)
def _clear_jti_cache():
    """Clear JTI replay cache between tests."""
    _jti_cache.clear()
    yield
    _jti_cache.clear()


# --- Test fixtures ---

# EC P-256 test key pair (for DPoP proofs)
_ec_private_key = ec.generate_private_key(ec.SECP256R1())
_ec_public_key = _ec_private_key.public_key()
_ec_public_numbers = _ec_public_key.public_numbers()


def _int_to_b64url(n: int, length: int) -> str:
    """Convert integer to base64url-encoded string."""
    raw = n.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


_test_jwk = {
    "kty": "EC",
    "crv": "P-256",
    "x": _int_to_b64url(_ec_public_numbers.x, 32),
    "y": _int_to_b64url(_ec_public_numbers.y, 32),
}

_test_jkt = _compute_jwk_thumbprint(_test_jwk)


def _make_dpop_proof(
    http_method: str = "GET",
    http_uri: str = "https://api.gostoa.dev/v1/apis",
    access_token: str = "test-access-token",
    jti: str = "unique-jti-1",
    iat: float | None = None,
    typ: str = "dpop+jwt",
) -> str:
    """Create a signed DPoP proof JWT for testing."""
    if iat is None:
        iat = time.time()

    ath = _compute_ath(access_token)
    claims = {
        "htm": http_method,
        "htu": http_uri,
        "ath": ath,
        "jti": jti,
        "iat": iat,
    }
    headers = {
        "typ": typ,
        "alg": "ES256",
        "jwk": _test_jwk,
    }

    private_pem = _ec_private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    )

    return jose_jwt.encode(claims, private_pem, algorithm="ES256", headers=headers)


# ============================================================
# mTLS Validation Tests
# ============================================================


class TestMtlsValidation:
    """Tests for RFC 8705 mTLS certificate-bound token validation."""

    def test_mtls_xfcc_match(self):
        """XFCC header fingerprint matches cnf.x5t#S256."""
        thumbprint = "dGVzdC10aHVtYnByaW50"
        hex_hash = base64.urlsafe_b64decode(thumbprint + "==").hex()
        cnf = {"x5t#S256": thumbprint}
        headers = {"x-forwarded-client-cert": f"Hash={hex_hash};Cert=...;Subject=CN=test"}

        result = _validate_mtls_binding(cnf, headers)
        assert result.valid is True
        assert result.mode == "mtls"

    def test_mtls_xfcc_mismatch(self):
        """XFCC header fingerprint does not match."""
        cnf = {"x5t#S256": "expected-thumbprint-value"}
        wrong_hash = hashlib.sha256(b"wrong-cert").hexdigest()
        headers = {"x-forwarded-client-cert": f"Hash={wrong_hash}"}

        result = _validate_mtls_binding(cnf, headers)
        assert result.valid is False
        assert "does not match" in result.error

    def test_mtls_no_cert_header(self):
        """No client certificate header present."""
        cnf = {"x5t#S256": "some-thumbprint"}
        headers = {}

        result = _validate_mtls_binding(cnf, headers)
        assert result.valid is False
        assert "none found" in result.error

    def test_mtls_missing_x5t(self):
        """Token has cnf but no x5t#S256 (handled by caller, but test edge case)."""
        cnf = {"x5t#S256": ""}
        headers = {"x-forwarded-client-cert": "Hash=abcd1234"}

        result = _validate_mtls_binding(cnf, headers)
        # Empty thumbprint won't match
        assert result.valid is False


# ============================================================
# DPoP Validation Tests
# ============================================================


class TestDpopValidation:
    """Tests for RFC 9449 DPoP validation."""

    def test_dpop_valid_proof(self):
        """Valid DPoP proof passes all checks."""
        cnf = {"jkt": _test_jkt}
        access_token = "test-access-token"
        proof = _make_dpop_proof(access_token=access_token)
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, access_token, "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is True
        assert result.mode == "dpop"

    def test_dpop_jkt_mismatch(self):
        """DPoP proof JWK thumbprint doesn't match cnf.jkt."""
        cnf = {"jkt": "wrong-thumbprint-value"}
        proof = _make_dpop_proof()
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "thumbprint" in result.error.lower()

    def test_dpop_htm_mismatch(self):
        """DPoP proof htm doesn't match actual HTTP method."""
        cnf = {"jkt": _test_jkt}
        proof = _make_dpop_proof(http_method="POST")
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "htm" in result.error.lower()

    def test_dpop_htu_mismatch(self):
        """DPoP proof htu doesn't match actual URI."""
        cnf = {"jkt": _test_jkt}
        proof = _make_dpop_proof(http_uri="https://other.example.com/api")
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "htu" in result.error.lower()

    def test_dpop_replay_detected(self):
        """Same jti used twice triggers replay detection."""
        cnf = {"jkt": _test_jkt}
        proof1 = _make_dpop_proof(jti="replay-jti")
        headers = {"dpop": proof1}

        # First use succeeds
        result1 = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result1.valid is True

        # Second use with same jti fails
        proof2 = _make_dpop_proof(jti="replay-jti")
        headers2 = {"dpop": proof2}
        result2 = _validate_dpop_binding(
            cnf, headers2, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result2.valid is False
        assert "replay" in result2.error.lower()

    def test_dpop_expired_iat(self):
        """DPoP proof with old iat fails freshness check."""
        cnf = {"jkt": _test_jkt}
        old_iat = time.time() - 300  # 5 minutes ago
        proof = _make_dpop_proof(iat=old_iat)
        headers = {"dpop": proof}

        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_DPOP_MAX_CLOCK_SKEW = 60
            result = _validate_dpop_binding(
                cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
            )
        assert result.valid is False
        assert "expired" in result.error.lower()

    def test_dpop_invalid_jwt(self):
        """Malformed DPoP proof JWT."""
        cnf = {"jkt": _test_jkt}
        headers = {"dpop": "not-a-jwt"}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False

    def test_dpop_wrong_typ(self):
        """DPoP proof with wrong typ header."""
        cnf = {"jkt": _test_jkt}
        proof = _make_dpop_proof(typ="at+jwt")
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "typ" in result.error.lower()

    def test_dpop_no_header(self):
        """No DPoP header present."""
        cnf = {"jkt": _test_jkt}
        headers = {}

        result = _validate_dpop_binding(
            cnf, headers, "test-access-token", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "none found" in result.error.lower()

    def test_dpop_ath_mismatch(self):
        """DPoP proof ath doesn't match actual access token."""
        cnf = {"jkt": _test_jkt}
        proof = _make_dpop_proof(access_token="token-A")
        headers = {"dpop": proof}

        result = _validate_dpop_binding(
            cnf, headers, "token-B", "GET", "https://api.gostoa.dev/v1/apis"
        )
        assert result.valid is False
        assert "ath" in result.error.lower()


# ============================================================
# Top-Level Validation Router Tests
# ============================================================


class TestValidateSenderConstrainedToken:
    """Tests for the top-level validate_sender_constrained_token function."""

    def test_disabled_always_passes(self):
        """When disabled, all tokens pass."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = False
            result = validate_sender_constrained_token(
                token_payload={}, access_token="t", headers={}, http_method="GET", http_uri="/"
            )
        assert result.valid is True
        assert result.mode == "disabled"

    def test_require_any_rejects_unbound(self):
        """require-any rejects tokens without cnf claim."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "require-any"
            result = validate_sender_constrained_token(
                token_payload={}, access_token="t", headers={}, http_method="GET", http_uri="/"
            )
        assert result.valid is False
        assert "cnf claim missing" in result.error

    def test_auto_allows_unbound(self):
        """auto strategy allows tokens without cnf claim."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "auto"
            result = validate_sender_constrained_token(
                token_payload={}, access_token="t", headers={}, http_method="GET", http_uri="/"
            )
        assert result.valid is True
        assert result.mode == "unbound"

    def test_routes_to_mtls(self):
        """Token with cnf.x5t#S256 routes to mTLS validation."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "require-any"
            result = validate_sender_constrained_token(
                token_payload={"cnf": {"x5t#S256": "test-thumbprint"}},
                access_token="t",
                headers={},
                http_method="GET",
                http_uri="/",
            )
        # Will fail because no cert header, but proves routing works
        assert result.mode == "mtls"

    def test_routes_to_dpop(self):
        """Token with cnf.jkt routes to DPoP validation."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "require-any"
            result = validate_sender_constrained_token(
                token_payload={"cnf": {"jkt": "test-jkt"}},
                access_token="t",
                headers={},
                http_method="GET",
                http_uri="/",
            )
        # Will fail because no DPoP header, but proves routing works
        assert result.mode == "dpop"

    def test_dpop_only_rejects_mtls(self):
        """dpop-only strategy rejects mTLS-bound tokens."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "dpop-only"
            result = validate_sender_constrained_token(
                token_payload={"cnf": {"x5t#S256": "test-thumbprint"}},
                access_token="t",
                headers={},
                http_method="GET",
                http_uri="/",
            )
        assert result.valid is False
        assert "dpop-only" in result.error

    def test_unrecognized_cnf_auto(self):
        """Auto mode passes unrecognized cnf claims."""
        with patch("src.auth.sender_constrained.settings") as mock_settings:
            mock_settings.SENDER_CONSTRAINED_ENABLED = True
            mock_settings.SENDER_CONSTRAINED_STRATEGY = "auto"
            result = validate_sender_constrained_token(
                token_payload={"cnf": {"unknown_key": "value"}},
                access_token="t",
                headers={},
                http_method="GET",
                http_uri="/",
            )
        assert result.valid is True
        assert result.mode == "unbound"


# ============================================================
# Utility Tests
# ============================================================


class TestUtilities:
    """Tests for helper functions."""

    def test_compute_ath(self):
        """ATH is SHA-256 of access token in base64url."""
        token = "test-token"
        ath = _compute_ath(token)
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert ath == expected

    def test_jwk_thumbprint_ec(self):
        """JWK thumbprint for EC key follows RFC 7638."""
        jwk = {"kty": "EC", "crv": "P-256", "x": "abc", "y": "def"}
        thumbprint = _compute_jwk_thumbprint(jwk)
        # Verify deterministic
        assert thumbprint == _compute_jwk_thumbprint(jwk)
        # Verify it's base64url
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for c in thumbprint
        )

    def test_jwk_thumbprint_rsa(self):
        """JWK thumbprint for RSA key follows RFC 7638."""
        jwk = {"kty": "RSA", "e": "AQAB", "n": "0vx7agoebGcQ..."}
        thumbprint = _compute_jwk_thumbprint(jwk)
        assert thumbprint  # Non-empty

    def test_extract_xfcc_fingerprint(self):
        """XFCC header Hash field extracted and converted to base64url."""
        hex_hash = hashlib.sha256(b"test-cert-der").hexdigest()
        headers = {"x-forwarded-client-cert": f"Hash={hex_hash};Subject=CN=test"}

        result = _extract_client_cert_fingerprint(headers)
        assert result is not None
        # Verify it's base64url of the same bytes
        expected = base64.urlsafe_b64encode(bytes.fromhex(hex_hash)).rstrip(b"=").decode()
        assert result == expected

    def test_extract_no_headers(self):
        """No certificate headers returns None."""
        result = _extract_client_cert_fingerprint({})
        assert result is None
