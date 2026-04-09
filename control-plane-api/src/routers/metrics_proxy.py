"""Authenticated Prometheus metrics proxy (CAB-2029).

Replaces the unauthenticated nginx /prometheus/ pass-through with JWT-validated
endpoints that inject tenant_id filtering into PromQL queries.

- cpi-admin: queries run unmodified (sees all tenants)
- tenant-admin/devops/viewer: tenant_id label injected into every PromQL query
"""

import re

from fastapi import APIRouter, Depends, Query

from ..auth.dependencies import User
from ..auth.rbac import require_role
from ..services.prometheus_client import PrometheusClient

router = APIRouter(prefix="/v1/metrics", tags=["Metrics"])

_READ_ROLES = ["cpi-admin", "tenant-admin", "devops", "viewer"]

# Singleton — shares config from settings
_prometheus = PrometheusClient()


def _inject_tenant_filter(promql: str, tenant_id: str) -> str:
    """Inject tenant_id label matcher into a PromQL query.

    Handles common patterns:
    - metric_name{...} → metric_name{..., tenant_id="X"}
    - metric_name → metric_name{tenant_id="X"}
    - sum(metric_name{...}) → sum(metric_name{..., tenant_id="X"})
    """
    tenant_filter = f'tenant_id="{tenant_id}"'

    def _add_to_selector(match: re.Match) -> str:
        name = match.group(1)
        existing = match.group(2).strip()
        if existing:
            return f"{name}{{{existing}, {tenant_filter}}}"
        return f"{name}{{{tenant_filter}}}"

    # Match metric_name{existing_labels} or metric_name{}
    result = re.sub(r"(\b[a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}", _add_to_selector, promql)

    # If no braces were found, try to add to bare metric names in common positions
    if result == promql and "{" not in promql:
        # Simple case: bare metric like "up" or "stoa_mcp_tools_calls_total"
        result = re.sub(
            r"(\b[a-zA-Z_:][a-zA-Z0-9_:]*\b)(?!\s*\()",
            rf"\1{{{tenant_filter}}}",
            promql,
            count=1,
        )

    return result


@router.get("/query")
async def prometheus_query(
    query: str = Query(..., description="PromQL instant query"),
    user: User = Depends(require_role(_READ_ROLES)),
):
    """Execute an authenticated Prometheus instant query.

    Tenant isolation: non-admin users have tenant_id injected into the PromQL.
    """
    promql = query
    if "cpi-admin" not in user.roles and user.tenant_id:
        promql = _inject_tenant_filter(query, user.tenant_id)

    result = await _prometheus.query(promql)
    if result is None:
        return {"status": "success", "data": {"resultType": "vector", "result": []}}

    return {"status": "success", "data": result}


@router.get("/query_range")
async def prometheus_query_range(
    query: str = Query(..., description="PromQL range query"),
    start: float = Query(..., description="Start timestamp (epoch seconds)"),
    end: float = Query(..., description="End timestamp (epoch seconds)"),
    step: str = Query("60s", description="Query resolution step"),
    user: User = Depends(require_role(_READ_ROLES)),
):
    """Execute an authenticated Prometheus range query.

    Tenant isolation: non-admin users have tenant_id injected into the PromQL.
    """
    from datetime import UTC, datetime

    promql = query
    if "cpi-admin" not in user.roles and user.tenant_id:
        promql = _inject_tenant_filter(query, user.tenant_id)

    start_dt = datetime.fromtimestamp(start, tz=UTC)
    end_dt = datetime.fromtimestamp(end, tz=UTC)

    result = await _prometheus.query_range(promql, start_dt, end_dt, step)
    if result is None:
        return {"status": "success", "data": {"resultType": "matrix", "result": []}}

    return {"status": "success", "data": result}
