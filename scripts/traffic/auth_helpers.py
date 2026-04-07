"""Auth helpers for the realistic traffic seeder.

Supports 5 auth strategies:
- api_key_query: API key as query parameter
- api_key_header: API key as HTTP header
- oauth2_cc: OAuth2 Client Credentials with token caching
- bearer: Pre-configured bearer token
- fapi_baseline: DPoP-bound access token (RFC 9449)
- fapi_advanced: DPoP + mTLS client certificate binding
- basic: HTTP Basic auth (for webMethods)
"""

import hashlib
import json
import logging
import os
import time
import uuid

import requests

logger = logging.getLogger("traffic-seeder.auth")

# ---------------------------------------------------------------------------
# Token Cache (in-memory, 5-minute TTL)
# ---------------------------------------------------------------------------

_token_cache: dict[str, tuple[str, float]] = {}
TOKEN_TTL = 300  # 5 minutes


def _get_cached_token(cache_key: str) -> str | None:
    """Return cached token if still valid, else None."""
    if cache_key in _token_cache:
        token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at:
            return token
        del _token_cache[cache_key]
    return None


def _set_cached_token(cache_key: str, token: str, ttl: int = TOKEN_TTL) -> None:
    """Cache a token with TTL."""
    _token_cache[cache_key] = (token, time.time() + ttl)


# ---------------------------------------------------------------------------
# OAuth2 Client Credentials
# ---------------------------------------------------------------------------


def fetch_oauth2_cc_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    scope: str = "stoa:read",
    timeout: int = 10,
) -> str | None:
    """Fetch OAuth2 token via client_credentials grant with caching.

    Args:
        token_url: Keycloak token endpoint
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        scope: Requested scope
        timeout: HTTP timeout in seconds

    Returns:
        Access token string, or None on failure
    """
    cache_key = f"oauth2_cc:{client_id}:{scope}"
    cached = _get_cached_token(cache_key)
    if cached:
        return cached

    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scope,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        # Cache for slightly less than the actual expiry
        ttl = min(data.get("expires_in", TOKEN_TTL) - 30, TOKEN_TTL)
        _set_cached_token(cache_key, token, max(ttl, 60))
        logger.debug("OAuth2 CC token acquired for %s", client_id)
        return token
    except Exception:
        logger.warning("OAuth2 CC token fetch failed for %s", client_id, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# DPoP Proof Generation (RFC 9449)
# ---------------------------------------------------------------------------


def generate_dpop_proof(
    url: str,
    method: str,
    signing_key_json: str | None = None,
) -> str | None:
    """Generate a DPoP proof JWT (RFC 9449).

    Uses PyJWT with cryptography backend for RS256 signing.
    If no signing key is provided, returns None (FAPI calls will
    proceed without DPoP — useful for testing the gateway's DPoP
    enforcement).

    Args:
        url: Target HTTP URL
        method: HTTP method (GET, POST)
        signing_key_json: JWK private key as JSON string

    Returns:
        DPoP proof JWT string, or None if key unavailable
    """
    if not signing_key_json:
        return None

    try:
        import jwt
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        key_data = json.loads(signing_key_json)

        # Build DPoP header + payload per RFC 9449
        jti = str(uuid.uuid4())
        now = int(time.time())

        headers = {
            "typ": "dpop+jwt",
            "alg": "RS256",
            "jwk": {
                "kty": key_data.get("kty", "RSA"),
                "n": key_data.get("n", ""),
                "e": key_data.get("e", "AQAB"),
            },
        }

        payload = {
            "jti": jti,
            "htm": method.upper(),
            "htu": url,
            "iat": now,
        }

        # Load private key
        if "d" in key_data:
            # JWK format — convert to PEM for PyJWT
            from jwt.algorithms import RSAAlgorithm

            private_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
        else:
            logger.warning("DPoP signing key missing private component 'd'")
            return None

        token = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
        return token
    except ImportError:
        logger.warning("PyJWT or cryptography not installed — DPoP disabled")
        return None
    except Exception:
        logger.warning("DPoP proof generation failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# mTLS Session
# ---------------------------------------------------------------------------


def setup_mtls_session(
    cert_path: str | None = None,
    key_path: str | None = None,
) -> requests.Session | None:
    """Create a requests.Session with mTLS client certificate.

    Args:
        cert_path: Path to client certificate PEM
        key_path: Path to client private key PEM

    Returns:
        Configured Session, or None if cert/key unavailable
    """
    if not cert_path or not key_path:
        return None
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        logger.warning("mTLS cert/key not found: %s / %s", cert_path, key_path)
        return None

    session = requests.Session()
    session.cert = (cert_path, key_path)
    session.timeout = (10, 30)
    return session


# ---------------------------------------------------------------------------
# Auth Applier — unified interface
# ---------------------------------------------------------------------------


def apply_auth(
    session: requests.Session,
    api_name: str,
    auth_type: str,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Apply auth credentials to request headers/params based on auth_type.

    Returns:
        Tuple of (updated_headers, updated_params)
    """
    h = dict(headers or {})
    p = dict(params or {})

    if auth_type == "none":
        pass

    elif auth_type == "api_key_query":
        from scripts.traffic.scenarios import OPENWEATHERMAP, ALPHAVANTAGE

        # Map API name to its key env var
        key_map = {
            "openweathermap": ("OPENWEATHERMAP_API_KEY", "appid"),
            "alphavantage": ("ALPHAVANTAGE_KEY", "apikey"),
        }
        if api_name in key_map:
            env_var, param_name = key_map[api_name]
            key = os.environ.get(env_var, "")
            if key:
                p[param_name] = key
        # Fallback: always send X-API-Key header so gateway detects api_key auth type
        if "Authorization" not in h and not any(k.lower() == "x-api-key" for k in h):
            h["X-API-Key"] = f"seed-{api_name}-{uuid.uuid4().hex[:8]}"

    elif auth_type == "api_key_header":
        key_map = {
            "newsapi": ("NEWSAPI_KEY", "X-Api-Key"),
        }
        applied = False
        if api_name in key_map:
            env_var, header_name = key_map[api_name]
            key = os.environ.get(env_var, "")
            if key:
                h[header_name] = key
                applied = True
        # Fallback: synthetic API key header for observability
        if not applied:
            h["X-API-Key"] = f"seed-{api_name}-{uuid.uuid4().hex[:8]}"

    elif auth_type == "oauth2_cc":
        kc_url = os.environ.get("KC_TOKEN_URL", "")
        client_id = os.environ.get("KC_CLIENT_ID", "")
        client_secret = os.environ.get("KC_CLIENT_SECRET", "")
        if kc_url and client_id and client_secret:
            token = fetch_oauth2_cc_token(kc_url, client_id, client_secret)
            if token:
                h["Authorization"] = f"Bearer {token}"
        # Fallback: synthetic Bearer for observability
        if "Authorization" not in h:
            h["Authorization"] = f"Bearer seed-oauth2-{uuid.uuid4().hex[:16]}"

    elif auth_type == "bearer":
        # Use the same OAuth2 CC token as bearer
        kc_url = os.environ.get("KC_TOKEN_URL", "")
        client_id = os.environ.get("KC_CLIENT_ID", "")
        client_secret = os.environ.get("KC_CLIENT_SECRET", "")
        if kc_url and client_id and client_secret:
            token = fetch_oauth2_cc_token(kc_url, client_id, client_secret, scope="stoa:read")
            if token:
                h["Authorization"] = f"Bearer {token}"
        # Fallback: synthetic Bearer for observability
        if "Authorization" not in h:
            h["Authorization"] = f"Bearer seed-bearer-{uuid.uuid4().hex[:16]}"

    elif auth_type == "fapi_baseline":
        # DPoP-bound token
        kc_url = os.environ.get("KC_TOKEN_URL", "")
        client_id = os.environ.get("KC_CLIENT_ID", "")
        client_secret = os.environ.get("KC_CLIENT_SECRET", "")
        dpop_key = os.environ.get("DPOP_SIGNING_KEY", "")
        if kc_url and client_id and client_secret:
            token = fetch_oauth2_cc_token(kc_url, client_id, client_secret, scope="stoa:read")
            if token:
                h["Authorization"] = f"DPoP {token}"
                proof = generate_dpop_proof(url, method, dpop_key or None)
                if proof:
                    h["DPoP"] = proof
        # Fallback: synthetic DPoP for observability
        if "Authorization" not in h:
            h["Authorization"] = f"DPoP seed-fapi-{uuid.uuid4().hex[:16]}"
            h["DPoP"] = f"seed-dpop-proof-{uuid.uuid4().hex[:16]}"

    elif auth_type == "fapi_advanced":
        # DPoP + mTLS — DPoP header applied, mTLS at session level
        kc_url = os.environ.get("KC_TOKEN_URL", "")
        client_id = os.environ.get("KC_CLIENT_ID", "")
        client_secret = os.environ.get("KC_CLIENT_SECRET", "")
        dpop_key = os.environ.get("DPOP_SIGNING_KEY", "")
        if kc_url and client_id and client_secret:
            token = fetch_oauth2_cc_token(kc_url, client_id, client_secret, scope="stoa:read stoa:write")
            if token:
                h["Authorization"] = f"DPoP {token}"
                proof = generate_dpop_proof(url, method, dpop_key or None)
                if proof:
                    h["DPoP"] = proof
        # Fallback: synthetic DPoP for observability
        if "Authorization" not in h:
            h["Authorization"] = f"DPoP seed-fapi-adv-{uuid.uuid4().hex[:16]}"
            h["DPoP"] = f"seed-dpop-proof-{uuid.uuid4().hex[:16]}"

    elif auth_type == "basic":
        # HTTP Basic for webMethods
        wm_user = os.environ.get("WM_ADMIN_USER", "Administrator")
        wm_pass = os.environ.get("WM_ADMIN_PASSWORD", "")
        if wm_pass:
            import base64

            credentials = base64.b64encode(f"{wm_user}:{wm_pass}".encode()).decode()
            h["Authorization"] = f"Basic {credentials}"
        # Fallback: synthetic Basic for observability
        if "Authorization" not in h:
            import base64

            credentials = base64.b64encode(b"seed-user:seed-pass").decode()
            h["Authorization"] = f"Basic {credentials}"

    return h, p
