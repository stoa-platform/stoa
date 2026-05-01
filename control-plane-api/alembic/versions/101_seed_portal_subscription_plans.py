"""seed default Portal subscription plans for published API tenants

Revision ID: 101_seed_portal_subscription_plans
Revises: 100_fix_webmethods_nonprod_urls
Create Date: 2026-05-01

Prod catalog tenants can expose Portal APIs before any subscription plans are
created for that provider tenant. The Portal then cannot complete the
subscription flow because plan selection is empty. This migration inserts a
minimal active self-service plan set only for tenants that currently publish at
least one Portal API and have zero active plans.
"""

import json
from collections.abc import Sequence
from uuid import NAMESPACE_DNS, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "101_seed_portal_subscription_plans"
down_revision: str | tuple[str, ...] | None = "100_fix_webmethods_nonprod_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATED_BY = "alembic:101_seed_portal_subscription_plans"
_SOURCE = "alembic-101-portal-default-plans"

_DEFAULT_PLANS = (
    {
        "slug": "portal-standard",
        "name": "Portal Standard",
        "description": "Self-service plan for validating a Portal subscription flow.",
        "rate_limit_per_second": 10,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 50_000,
        "monthly_request_limit": 1_000_000,
        "burst_limit": 20,
        "requires_approval": False,
    },
    {
        "slug": "portal-premium",
        "name": "Portal Premium",
        "description": "Higher-volume plan for production-like Portal validation.",
        "rate_limit_per_second": 50,
        "rate_limit_per_minute": 3_000,
        "daily_request_limit": 500_000,
        "monthly_request_limit": 10_000_000,
        "burst_limit": 100,
        "requires_approval": True,
    },
)


def _plan_id(tenant_id: str, slug: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"stoa:portal-default-plan:{tenant_id}:{slug}"))


def upgrade() -> None:
    conn = op.get_bind()
    tenant_ids = (
        conn.execute(
            sa.text("""
                SELECT DISTINCT c.tenant_id
                FROM api_catalog c
                WHERE c.portal_published IS TRUE
                  AND c.deleted_at IS NULL
                  AND COALESCE(c.tenant_id, '') <> ''
                  AND NOT EXISTS (
                    SELECT 1
                    FROM plans p
                    WHERE p.tenant_id = c.tenant_id
                      AND p.status = 'active'
                  )
                ORDER BY c.tenant_id
            """)
        )
        .scalars()
        .all()
    )

    for tenant_id in tenant_ids:
        for plan in _DEFAULT_PLANS:
            metadata = {
                "source": _SOURCE,
                "scope": "portal-default",
                "tenant_id": tenant_id,
                "requests_per_minute": plan["rate_limit_per_minute"],
            }
            conn.execute(
                sa.text("""
                    INSERT INTO plans (
                        id, slug, name, description, tenant_id,
                        rate_limit_per_second, rate_limit_per_minute,
                        daily_request_limit, monthly_request_limit, burst_limit,
                        requires_approval, status, pricing_metadata, created_by
                    )
                    VALUES (
                        :id, :slug, :name, :description, :tenant_id,
                        :rate_limit_per_second, :rate_limit_per_minute,
                        :daily_request_limit, :monthly_request_limit, :burst_limit,
                        :requires_approval, 'active', CAST(:pricing_metadata AS json), :created_by
                    )
                    ON CONFLICT (tenant_id, slug) DO NOTHING
                """),
                {
                    "id": _plan_id(str(tenant_id), str(plan["slug"])),
                    "slug": plan["slug"],
                    "name": plan["name"],
                    "description": plan["description"],
                    "tenant_id": tenant_id,
                    "rate_limit_per_second": plan["rate_limit_per_second"],
                    "rate_limit_per_minute": plan["rate_limit_per_minute"],
                    "daily_request_limit": plan["daily_request_limit"],
                    "monthly_request_limit": plan["monthly_request_limit"],
                    "burst_limit": plan["burst_limit"],
                    "requires_approval": plan["requires_approval"],
                    "pricing_metadata": json.dumps(metadata),
                    "created_by": _CREATED_BY,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM plans
            WHERE created_by = :created_by
              AND pricing_metadata->>'source' = :source
        """),
        {"created_by": _CREATED_BY, "source": _SOURCE},
    )
