"""Runtime deployment summaries for API catalog list views."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gateway_deployment import GatewayDeployment
from src.models.gateway_instance import GatewayInstance

logger = logging.getLogger(__name__)

_STATUS_PRIORITY = {
    "error": 60,
    "drifted": 50,
    "syncing": 40,
    "pending": 30,
    "deleting": 20,
    "synced": 10,
}


async def load_api_runtime_deployment_summaries(
    session: AsyncSession,
    catalog_ids: list[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    """Return per-environment GatewayDeployment summaries keyed by APICatalog.id.

    The API catalog list remains usable if the enrichment query fails; the
    detail lifecycle endpoint remains the authoritative place for exact rows.
    """

    if not catalog_ids:
        return {}

    try:
        stmt = (
            select(GatewayDeployment, GatewayInstance)
            .join(GatewayInstance, GatewayDeployment.gateway_instance_id == GatewayInstance.id)
            .where(
                GatewayDeployment.api_catalog_id.in_(catalog_ids),
                GatewayInstance.deleted_at.is_(None),
            )
            .order_by(GatewayInstance.environment, GatewayInstance.name)
        )
        result = await session.execute(stmt)
    except Exception as exc:  # pragma: no cover - defensive enrichment fallback
        logger.warning("Failed to load API runtime deployment summaries: %s", exc)
        return {}

    grouped: dict[tuple[UUID, str], list[tuple[GatewayDeployment, GatewayInstance]]] = defaultdict(list)
    for deployment, gateway in result.all():
        grouped[(deployment.api_catalog_id, gateway.environment)].append((deployment, gateway))

    summaries: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for (catalog_id, environment), rows in grouped.items():
        statuses = [_status_value(deployment.sync_status) for deployment, _gateway in rows]
        aggregate_status = max(statuses, key=lambda status: _STATUS_PRIORITY.get(status, 0))
        latest_error = _latest_error(rows)
        latest_success = _latest_sync_success(rows)
        summaries[catalog_id].append(
            {
                "environment": environment,
                "status": aggregate_status,
                "gateway_count": len(rows),
                "synced_count": sum(1 for status in statuses if status == "synced"),
                "error_count": sum(1 for status in statuses if status == "error"),
                "pending_count": sum(1 for status in statuses if status in {"pending", "syncing"}),
                "drifted_count": sum(1 for status in statuses if status == "drifted"),
                "latest_error": latest_error,
                "last_sync_success": latest_success,
                "gateway_names": [gateway.name for _deployment, gateway in rows],
            }
        )

    return dict(summaries)


def _status_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def _latest_error(rows: list[tuple[GatewayDeployment, GatewayInstance]]) -> str | None:
    errored = [
        deployment
        for deployment, _gateway in rows
        if deployment.sync_error or _status_value(deployment.sync_status) in {"error", "drifted"}
    ]
    if not errored:
        return None
    errored.sort(key=lambda deployment: deployment.last_sync_attempt or deployment.updated_at, reverse=True)
    return errored[0].sync_error


def _latest_sync_success(rows: list[tuple[GatewayDeployment, GatewayInstance]]) -> datetime | None:
    successes = [deployment.last_sync_success for deployment, _gateway in rows if deployment.last_sync_success]
    return max(successes) if successes else None
