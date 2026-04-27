"""catalog_content_hash — deterministic SHA-256 of the api.yaml bytes.

Spec §6.2.1 (CAB-2182 B-HASH).

Distinct from ``compute_uac_spec_hash`` (UAC V2, out-of-scope this cycle —
spec §4.2 ``Cycle UAC V2``).
"""

from __future__ import annotations

import hashlib

CatalogContentHash = str


def compute_catalog_content_hash(api_yaml_bytes: bytes) -> CatalogContentHash:
    """Return ``sha256_hex(api_yaml_bytes)``.

    Idempotency anchor for the GitOps create flow (spec §6.2.1).

    Raises:
        TypeError: if ``api_yaml_bytes`` is not ``bytes`` (str rejected so the
            caller cannot bypass the encoding step).
    """
    if not isinstance(api_yaml_bytes, bytes):
        raise TypeError("api_yaml_bytes must be bytes, not str")
    return hashlib.sha256(api_yaml_bytes).hexdigest()
