"""Canonical path builder for ``stoa-catalog``.

Spec §6.1 + §6.5 step 6 + §6.10 + §6.14 (CAB-2183 B-LAYOUT, CAB-2187 B10).

The canonical layout is::

    tenants/{tenant_id}/apis/{api_name}/api.yaml

Both segments are slugs (``[a-z0-9-]+``). UUID-shaped values are refused at
construction time so that the bug B10 (``api_catalog.id`` PK leaking into
``git_path``) cannot reappear via this module.
"""

from __future__ import annotations

import re

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_CANONICAL_PATH_PATTERN = re.compile(r"^tenants/([^/]+)/apis/([^/]+)/api\.yaml$")


def is_uuid_shaped(value: str) -> bool:
    """Return True if ``value`` matches a canonical UUID v1-v5 representation.

    Used as the gate for §6.4 (``api_id`` and ``git_path`` MUST stay slug).
    """
    return bool(_UUID_PATTERN.match(value))


def _validate_slug_segment(segment: str, *, name: str) -> None:
    if not segment:
        raise ValueError(f"{name} must be non-empty")
    if "/" in segment or " " in segment:
        raise ValueError(f"unsafe path segment for {name}: {segment!r}")
    if ".." in segment or segment.startswith("."):
        raise ValueError(f"unsafe path segment for {name}: {segment!r}")


def canonical_catalog_path(tenant_id: str, api_name: str) -> str:
    """Return the canonical ``api.yaml`` path for ``(tenant_id, api_name)``.

    Refuses:

    * empty segments,
    * UUID-shaped ``tenant_id`` or ``api_name`` (CAB-2187 B10 garde-fou §9.10),
    * segments containing ``/``, ``..``, leading ``.``, or whitespace.
    """
    _validate_slug_segment(tenant_id, name="tenant_id")
    _validate_slug_segment(api_name, name="api_name")

    if is_uuid_shaped(api_name):
        raise ValueError(
            f"api_name UUID-shaped not allowed: {api_name!r}. "
            "Violates §6.4 (no PK leak into git_path). See CAB-2187 (B10)."
        )
    if is_uuid_shaped(tenant_id):
        raise ValueError(f"tenant_id UUID-shaped not allowed: {tenant_id!r}. Violates §6.4 (no PK leak into git_path).")

    return f"tenants/{tenant_id}/apis/{api_name}/api.yaml"


def parse_canonical_path(git_path: str) -> tuple[str, str]:
    """Inverse of :func:`canonical_catalog_path`.

    Refuses non-canonical paths and any segment that is UUID-shaped.

    Returns ``(tenant_id, api_name)``.
    """
    match = _CANONICAL_PATH_PATTERN.match(git_path)
    if not match:
        raise ValueError(f"non-canonical catalog path: {git_path!r}")

    tenant_id, api_name = match.group(1), match.group(2)

    if is_uuid_shaped(tenant_id) or is_uuid_shaped(api_name):
        raise ValueError(
            f"UUID-shaped segment in path: tenant_id={tenant_id!r}, api_name={api_name!r}. See §6.4 + CAB-2187 (B10)."
        )

    return tenant_id, api_name
