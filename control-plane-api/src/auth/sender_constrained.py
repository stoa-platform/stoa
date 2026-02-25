"""Sender-Constrained Token Validation (CAB-438).

Implements RFC 8705 (mTLS Certificate-Bound Tokens) and RFC 9449 (DPoP)
for the control-plane-api. Called from get_current_user() after JWT decode.

Strategies:
- auto: allow unbound tokens (migration mode)
- require-any: require either mTLS or DPoP binding
- mtls-only: require mTLS binding only
- dpop-only: require DPoP binding only
"""

import base64
import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass

from jose import jwt as jose_jwt

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)

# In-memory JTI replay cache (production: use Redis)
_jti_cache: dict[str, float] = {}
_JTI_CACHE_MAX_SIZE = 10000
_JTI_TTL_SECONDS = 300  # 5 minutes


@dataclass
class SenderConstrainedResult:
    """Result of sender-constrained token validation."""

    valid: bool
    mode: str  # "disabled", "mtls", "dpop", "unbound", "skipped"
    error: str | None = None


def validate_sender_constrained_token(
    token_payload: dict,
    access_token: str,
    headers: dict[str, str],
    http_method: str,
    http_uri: str,
) -> SenderConstrainedResult:
    """Validate sender-constrained token binding.

    Routes to mTLS or DPoP validation based on the token's cnf claim.

    Args:
        token_payload: Decoded JWT payload.
        access_token: Raw access token string (for DPoP ath computation).
        headers: Lowercased request headers dict.
        http_method: HTTP method (GET, POST, etc.).
        http_uri: Full request URI.

    Returns:
        SenderConstrainedResult with validation outcome.
    """
    if not settings.SENDER_CONSTRAINED_ENABLED:
        return SenderConstrainedResult(valid=True, mode="disabled")

    strategy = settings.SENDER_CONSTRAINED_STRATEGY
    cnf = token_payload.get("cnf")

    # No binding claim in token
    if not cnf:
        if strategy == "auto":
            return SenderConstrainedResult(valid=True, mode="unbound")
        return SenderConstrainedResult(
            valid=False,
            mode="unbound",
            error=f"Token has no sender binding (cnf claim missing), strategy={strategy}",
        )

    # Route based on cnf content
    if "x5t#S256" in cnf:
        if strategy == "dpop-only":
            return SenderConstrainedResult(
                valid=False,
                mode="mtls",
                error="mTLS binding found but strategy is dpop-only",
            )
        return _validate_mtls_binding(cnf, headers)

    if "jkt" in cnf:
        if strategy == "mtls-only":
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP binding found but strategy is mtls-only",
            )
        return _validate_dpop_binding(cnf, headers, access_token, http_method, http_uri)

    # Unrecognized cnf claim
    if strategy == "auto":
        logger.warning("Unrecognized cnf claim keys", cnf_keys=list(cnf.keys()))
        return SenderConstrainedResult(valid=True, mode="unbound")

    return SenderConstrainedResult(
        valid=False,
        mode="unbound",
        error=f"Unrecognized cnf claim: {list(cnf.keys())}",
    )


# --- mTLS Validation (RFC 8705) ---


def _validate_mtls_binding(cnf: dict, headers: dict[str, str]) -> SenderConstrainedResult:
    """Validate mTLS certificate-bound token (RFC 8705).

    Compares cnf.x5t#S256 from the token against the client certificate
    fingerprint from proxy headers (XFCC or x-ssl-client-cert).
    """
    expected_thumbprint = cnf["x5t#S256"]
    cert_fingerprint = _extract_client_cert_fingerprint(headers)

    if not cert_fingerprint:
        return SenderConstrainedResult(
            valid=False,
            mode="mtls",
            error="mTLS binding requires client certificate but none found in headers",
        )

    if cert_fingerprint != expected_thumbprint:
        logger.warning(
            "mTLS certificate thumbprint mismatch",
            expected=expected_thumbprint[:8] + "...",
            got=cert_fingerprint[:8] + "...",
        )
        return SenderConstrainedResult(
            valid=False,
            mode="mtls",
            error="Client certificate does not match token binding",
        )

    return SenderConstrainedResult(valid=True, mode="mtls")


def _extract_client_cert_fingerprint(headers: dict[str, str]) -> str | None:
    """Extract client certificate SHA-256 fingerprint from proxy headers.

    Supports:
    - x-forwarded-client-cert (XFCC, Envoy/Istio format): Hash=<hex>;...
    - x-ssl-client-cert (nginx): URL-encoded PEM certificate
    """
    # XFCC header (Envoy/Istio) — Hash field is SHA-256 hex
    xfcc = headers.get("x-forwarded-client-cert", "")
    if xfcc:
        for part in xfcc.split(";"):
            part = part.strip()
            if part.lower().startswith("hash="):
                hex_hash = part[5:]
                # Convert hex to base64url (RFC 8705 uses base64url)
                raw = bytes.fromhex(hex_hash)
                return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    # nginx x-ssl-client-cert — URL-encoded PEM
    cert_pem = headers.get("x-ssl-client-cert", "")
    if cert_pem:
        try:
            decoded_pem = urllib.parse.unquote(cert_pem)
            from ..services.certificate_utils import parse_pem_certificate

            cert_info = parse_pem_certificate(decoded_pem)
            return cert_info.fingerprint_b64url
        except (ValueError, ImportError):
            logger.warning("Failed to parse x-ssl-client-cert header")

    return None


# --- DPoP Validation (RFC 9449) ---


def _validate_dpop_binding(
    cnf: dict,
    headers: dict[str, str],
    access_token: str,
    http_method: str,
    http_uri: str,
) -> SenderConstrainedResult:
    """Validate DPoP proof (RFC 9449).

    5-step validation:
    1. Extract DPoP proof JWT from header
    2. Decode proof, verify typ=dpop+jwt
    3. Compute JWK thumbprint (RFC 7638), compare to cnf.jkt
    4. Validate htm, htu, ath claims
    5. Check jti for replay
    """
    dpop_proof = headers.get("dpop", "")
    if not dpop_proof:
        return SenderConstrainedResult(
            valid=False,
            mode="dpop",
            error="DPoP binding requires DPoP header but none found",
        )

    try:
        # Step 1-2: Decode proof header (unverified) to get JWK
        proof_header = jose_jwt.get_unverified_header(dpop_proof)
        if proof_header.get("typ", "").lower() != "dpop+jwt":
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error=f"DPoP proof has wrong typ: {proof_header.get('typ')}",
            )

        jwk = proof_header.get("jwk")
        if not jwk:
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP proof missing jwk in header",
            )

        # Step 3: Compute JWK thumbprint and compare to cnf.jkt
        thumbprint = _compute_jwk_thumbprint(jwk)
        expected_jkt = cnf["jkt"]
        if thumbprint != expected_jkt:
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP JWK thumbprint does not match token binding (cnf.jkt)",
            )

        # Decode proof claims (verify signature with embedded JWK)
        from jose import jwk as jose_jwk

        algorithm = proof_header.get("alg", "ES256")
        key = jose_jwk.construct(jwk, algorithm=algorithm)
        proof_claims = jose_jwt.decode(
            dpop_proof,
            key,
            algorithms=[algorithm],
            options={"verify_aud": False, "verify_sub": False},
        )

        # Step 4: Validate htm, htu, ath
        if proof_claims.get("htm", "").upper() != http_method.upper():
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error=f"DPoP htm mismatch: expected {http_method}, got {proof_claims.get('htm')}",
            )

        proof_htu = proof_claims.get("htu", "")
        # Compare scheme + host + path (ignore query string)
        if _normalize_uri(proof_htu) != _normalize_uri(http_uri):
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error=f"DPoP htu mismatch: expected {http_uri}, got {proof_htu}",
            )

        # Verify ath (access token hash)
        expected_ath = _compute_ath(access_token)
        proof_ath = proof_claims.get("ath", "")
        if proof_ath != expected_ath:
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP ath (access token hash) mismatch",
            )

        # Verify iat freshness
        iat = proof_claims.get("iat", 0)
        now = time.time()
        max_skew = settings.SENDER_CONSTRAINED_DPOP_MAX_CLOCK_SKEW
        if abs(now - iat) > max_skew:
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error=f"DPoP proof expired (iat={iat}, now={now:.0f}, skew={max_skew}s)",
            )

        # Step 5: Replay prevention (jti)
        jti = proof_claims.get("jti", "")
        if not jti:
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP proof missing jti claim",
            )
        if _is_jti_replayed(jti):
            return SenderConstrainedResult(
                valid=False,
                mode="dpop",
                error="DPoP proof jti already used (replay detected)",
            )

        return SenderConstrainedResult(valid=True, mode="dpop")

    except Exception as e:
        logger.warning("DPoP validation error", error=str(e), error_type=type(e).__name__)
        return SenderConstrainedResult(
            valid=False,
            mode="dpop",
            error=f"DPoP validation failed: {e}",
        )


def _compute_jwk_thumbprint(jwk: dict) -> str:
    """Compute JWK Thumbprint per RFC 7638.

    Canonical JSON of required members -> SHA-256 -> base64url.
    """
    kty = jwk.get("kty", "")

    # Required members per key type (RFC 7638 Section 3.2)
    if kty == "EC":
        canonical = {"crv": jwk["crv"], "kty": kty, "x": jwk["x"], "y": jwk["y"]}
    elif kty == "RSA":
        canonical = {"e": jwk["e"], "kty": kty, "n": jwk["n"]}
    elif kty == "OKP":
        canonical = {"crv": jwk["crv"], "kty": kty, "x": jwk["x"]}
    else:
        raise ValueError(f"Unsupported key type for JWK thumbprint: {kty}")

    # JSON serialization with sorted keys, no whitespace
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _compute_ath(access_token: str) -> str:
    """Compute access token hash (ath) for DPoP.

    SHA-256 of the ASCII access token -> base64url.
    """
    digest = hashlib.sha256(access_token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _normalize_uri(uri: str) -> str:
    """Normalize URI for DPoP htu comparison (scheme + host + path only)."""
    parsed = urllib.parse.urlparse(uri)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _is_jti_replayed(jti: str) -> bool:
    """Check if JTI has been seen before (in-memory replay cache)."""
    global _jti_cache
    now = time.time()

    # Evict expired entries periodically
    if len(_jti_cache) > _JTI_CACHE_MAX_SIZE:
        expired = [k for k, v in _jti_cache.items() if now - v > _JTI_TTL_SECONDS]
        for k in expired:
            del _jti_cache[k]

    if jti in _jti_cache:
        return True

    _jti_cache[jti] = now
    return False
