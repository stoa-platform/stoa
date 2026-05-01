"""Tenant eligibility helpers for the GitOps create path."""

from __future__ import annotations

from collections.abc import Iterable


def is_gitops_create_eligible(
    *,
    enabled: bool,
    tenant_id: str,
    eligible_tenants: Iterable[str],
) -> bool:
    """Return True when ``POST /apis`` must use the Git-first writer.

    ``GITOPS_ELIGIBLE_TENANTS`` remains default-empty for conservative rollout,
    but ops can now set ``*`` to route every tenant through the GitOps path once
    the backfill has made the catalog authoritative.
    """
    if not enabled:
        return False
    eligible = {tenant.strip() for tenant in eligible_tenants if tenant and tenant.strip()}
    return "*" in eligible or tenant_id in eligible
