#!/usr/bin/env python3
"""Mock JWT generator for mTLS demo (CAB-1025).

Generates access tokens with RFC 8705 certificate binding:
- Standard claims: sub, iss, aud, exp, iat
- cnf.x5t#S256: certificate fingerprint (base64url)

Uses python-jose HS256 for demo simplicity. NOT for production.

Usage:
    python scripts/demo-mtls/mock_jwt.py          # Print sample token
    python -c "from scripts.demo_mtls.mock_jwt import generate_demo_token; ..."
"""

import sys
import time
from pathlib import Path

# Add control-plane-api/src to path for fingerprint_utils
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "control-plane-api"))

from jose import jwt  # python-jose
from src.services.fingerprint_utils import hex_to_base64url

# Demo signing key — NOT for production
DEMO_SECRET = "stoa-demo-secret-key-do-not-use-in-production"  # nosec
DEMO_ISSUER = "https://demo.gostoa.dev/auth"
DEMO_AUDIENCE = "stoa-api"


def generate_demo_token(
    client_id: str,
    tenant_id: str,
    certificate_fingerprint_hex: str,
    expires_in: int = 3600,
    roles: list[str] | None = None,
) -> str:
    """Generate a demo JWT with cnf certificate binding.

    Args:
        client_id: The client identifier (sub claim).
        tenant_id: Tenant for RBAC.
        certificate_fingerprint_hex: Cert SHA-256 fingerprint in hex (64 chars).
        expires_in: Token lifetime in seconds.
        roles: Optional roles list.

    Returns:
        Signed JWT string.
    """
    now = int(time.time())

    payload = {
        "sub": client_id,
        "iss": DEMO_ISSUER,
        "aud": DEMO_AUDIENCE,
        "iat": now,
        "exp": now + expires_in,
        "tenant_id": tenant_id,
        "roles": roles or ["api:read", "api:write"],
        "cnf": {
            "x5t#S256": hex_to_base64url(certificate_fingerprint_hex),
        },
    }

    return jwt.encode(payload, DEMO_SECRET, algorithm="HS256")


def generate_mismatched_token(
    client_id: str,
    tenant_id: str,
) -> str:
    """Generate a token with wrong fingerprint (for 401 demo)."""
    return generate_demo_token(
        client_id, tenant_id, "00" * 32,
    )


def generate_no_cnf_token(
    client_id: str,
    tenant_id: str,
) -> str:
    """Generate a token without cnf claim (client_secret flow)."""
    now = int(time.time())
    payload = {
        "sub": client_id,
        "iss": DEMO_ISSUER,
        "aud": DEMO_AUDIENCE,
        "iat": now,
        "exp": now + 3600,
        "tenant_id": tenant_id,
    }
    return jwt.encode(payload, DEMO_SECRET, algorithm="HS256")


if __name__ == "__main__":
    import json
    import base64

    sample_fp = "84b99532f8e79829bf23877cff79f0e484b99532f8e79829bf23877cff79f0e4"
    token = generate_demo_token("demo-client-001", "acme", sample_fp)

    # Decode and display
    parts = token.split(".")
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))

    print("=== Demo JWT (CAB-1025) ===")
    print(f"\nToken ({len(token)} chars):")
    print(f"  {token[:80]}...")
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))
    print(f"\ncnf.x5t#S256: {payload['cnf']['x5t#S256']}")
    print(f"Original hex:  {sample_fp}")
