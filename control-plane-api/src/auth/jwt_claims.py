"""Preserve the existing claim rules when decoding with PyJWT."""

import time
from typing import Any

from jwt import ExpiredSignatureError, InvalidTokenError


def validate_legacy_claims(claims: dict[str, Any]) -> None:
    """Validate NumericDates without rejecting future iat or requiring exp."""
    for claim, label in (("iat", "Issued At"), ("exp", "Expiration Time")):
        if claim not in claims:
            continue
        try:
            value = int(claims[claim])
        except (TypeError, ValueError):
            raise InvalidTokenError(f"{label} claim ({claim}) must be an integer.") from None
        # The previous decoder compared integer seconds, accepting exp == now.
        if claim == "exp" and value < int(time.time()):
            raise ExpiredSignatureError("Signature has expired.")
    # These paths decode access tokens/proofs, without a companion access token
    # to check an OIDC at_hash. The previous decoder rejected that claim.
    if "at_hash" in claims:
        raise InvalidTokenError("No access_token provided to compare against at_hash claim.")
