"""Portal publication tag policy.

Legacy catalog imports used free-form tags to publish APIs to the portal. The
canonical lifecycle now owns publication, so these tags are either rejected on
HTTP write paths or stripped from catalog imports.
"""

from __future__ import annotations

from collections.abc import Iterable

LEGACY_PORTAL_PUBLICATION_TAGS = frozenset({"portal:published", "promoted:portal", "portal-promoted"})


def find_legacy_portal_publication_tags(tags: Iterable[object] | None) -> list[str]:
    """Return legacy portal publication tags found in ``tags``."""
    found: list[str] = []
    for tag in tags or []:
        normalized = str(tag).strip()
        if normalized.lower() in LEGACY_PORTAL_PUBLICATION_TAGS:
            found.append(normalized)
    return found


def strip_legacy_portal_publication_tags(tags: Iterable[object] | None) -> tuple[list[str], list[str]]:
    """Return ``(clean_tags, stripped_tags)`` without legacy portal markers."""
    clean: list[str] = []
    stripped: list[str] = []
    for tag in tags or []:
        normalized = str(tag).strip()
        if not normalized:
            continue
        if normalized.lower() in LEGACY_PORTAL_PUBLICATION_TAGS:
            stripped.append(normalized)
            continue
        clean.append(normalized)
    return clean, stripped
