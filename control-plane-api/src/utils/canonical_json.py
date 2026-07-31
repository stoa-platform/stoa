"""Canonical JSON hashing shared with stoa-gateway approval tokens."""

import hashlib
import json
from typing import Any


def canonical_hash(obj: Any) -> str:
    payload = {} if obj is None else obj
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
