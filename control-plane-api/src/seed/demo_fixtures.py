"""Deterministic demo fixtures for the multi-client Customer API scenario (CAB-2149).

Backbone of CAB-2148 Phase 1. Single source of truth consumed by
``src.db.reset_service`` and ``scripts.demo.reset``. Neutral placeholder
tenants (``tenant-a/b/c/d``) — client identities are injected at presentation
time via narrative, never here (pre-push OpSec scanner rejects identifying
phrases). All identifiers are derived so two cold runs produce identical rows.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

DEMO_TENANTS: tuple[dict[str, str], ...] = (
    {"id": "tenant-a", "name": "Tenant A", "description": "Demo tenant A (placeholder)."},
    {"id": "tenant-b", "name": "Tenant B", "description": "Demo tenant B (placeholder)."},
    {"id": "tenant-c", "name": "Tenant C", "description": "Demo tenant C (placeholder)."},
    {"id": "tenant-d", "name": "Tenant D", "description": "Demo tenant D (placeholder)."},
)

# Neutral Customer API scenario — replicated identically across every tenant
# to demonstrate UAC "Define Once, Expose Everywhere".
CUSTOMER_API_ID = "customer-api-v1"
CUSTOMER_API_NAME = "Customer API"
CUSTOMER_API_VERSION = "1.0.0"
CUSTOMER_API_CATEGORY = "reference-data"
CUSTOMER_API_TAGS: tuple[str, ...] = ("customer", "referentiel", "uac-demo")
CUSTOMER_API_AUDIENCE = "internal"
CUSTOMER_API_DESCRIPTION = (
    "Neutral customer reference-data API used by the UAC 5-step demo scenario. "
    "Identical definition replicated across every demo tenant."
)


@dataclass(frozen=True)
class DemoAPIFixture:
    """One Customer API catalog row, scoped to a single tenant."""

    tenant_id: str
    api_id: str
    api_name: str
    version: str
    category: str
    audience: str
    tags: tuple[str, ...]
    description: str

    @property
    def deterministic_uuid(self) -> UUID:
        """Stable UUID derived from ``(tenant_id, api_id, version)``.

        SHA-256 of the identity tuple, truncated to 16 bytes. Collision
        probability is negligible in a 4-tenant catalogue.
        """
        seed = f"demo:{self.tenant_id}:{self.api_id}:{self.version}".encode()
        return UUID(bytes=hashlib.sha256(seed).digest()[:16], version=5)

    def metadata(self) -> dict[str, Any]:
        """JSON-serialisable metadata payload for the catalog row."""
        return {
            "source": "demo-seeder",
            "scenario": "customer-api-uac-demo",
            "name": self.api_name,
            "version": self.version,
            "description": self.description,
            "backend_url": f"https://api.gostoa.dev/demo/{self.tenant_id}/customers",
            "auth_type": "none",
        }


@dataclass(frozen=True)
class DemoTenantFixture:
    """Tenant definition + its attached Customer API row."""

    id: str
    name: str
    description: str
    api: DemoAPIFixture


def _build_demo_fixtures() -> tuple[DemoTenantFixture, ...]:
    """Build the deterministic fixture tuple. Pure function — no I/O, no clock."""
    rows = [
        DemoTenantFixture(
            id=tenant["id"],
            name=tenant["name"],
            description=tenant["description"],
            api=DemoAPIFixture(
                tenant_id=tenant["id"],
                api_id=CUSTOMER_API_ID,
                api_name=CUSTOMER_API_NAME,
                version=CUSTOMER_API_VERSION,
                category=CUSTOMER_API_CATEGORY,
                audience=CUSTOMER_API_AUDIENCE,
                tags=CUSTOMER_API_TAGS,
                description=CUSTOMER_API_DESCRIPTION,
            ),
        )
        for tenant in DEMO_TENANTS
    ]
    # Lock ordering so byte-identical snapshots are reproducible.
    rows.sort(key=lambda t: t.id)
    return tuple(rows)


DEMO_FIXTURES: tuple[DemoTenantFixture, ...] = _build_demo_fixtures()


@dataclass(frozen=True)
class DemoFixtureBundle:
    """Immutable envelope around the full demo catalogue."""

    tenants: tuple[DemoTenantFixture, ...] = field(default_factory=_build_demo_fixtures)

    @property
    def tenant_ids(self) -> tuple[str, ...]:
        return tuple(t.id for t in self.tenants)

    def apis_for(self, tenant_id: str) -> tuple[DemoAPIFixture, ...]:
        return tuple(t.api for t in self.tenants if t.id == tenant_id)


def default_bundle() -> DemoFixtureBundle:
    """Return the canonical immutable demo bundle."""
    return DemoFixtureBundle()
