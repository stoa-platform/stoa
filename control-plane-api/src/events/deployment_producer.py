"""Deployment lifecycle event producer (CAB-1410).

Publishes structured events to stoa.deployment.events so downstream
consumers (e.g. Notification Service — CAB-1413) can react to
deployment state transitions without polling the CP API.

Topic: stoa.deployment.events  (Topics.DEPLOYMENT_EVENTS)
Event types:
    deployment.started      — deployment record created, gateway work queued
    deployment.completed    — gateway reported SUCCESS
    deployment.failed       — gateway reported FAILED
    deployment.rolledback   — rollback deployment completed
"""

import logging
from typing import TYPE_CHECKING

from ..services.kafka_service import Topics, kafka_service

if TYPE_CHECKING:
    from ..models.deployment import Deployment

logger = logging.getLogger(__name__)

_SYSTEM_USER = "system"


def _deployment_payload(deployment: "Deployment") -> dict:
    """Build a canonical deployment event payload."""
    return {
        "deployment_id": str(deployment.id),
        "tenant_id": deployment.tenant_id,
        "api_id": deployment.api_id,
        "api_name": deployment.api_name,
        "environment": deployment.environment,
        "version": deployment.version,
        "status": deployment.status,
        "deployed_by": deployment.deployed_by,
        "gateway_id": deployment.gateway_id,
        "rollback_of": str(deployment.rollback_of) if deployment.rollback_of else None,
    }


async def emit_deployment_started(deployment: "Deployment") -> str:
    """Emit deployment.started when a new deploy is queued."""
    payload = _deployment_payload(deployment)
    try:
        return await kafka_service.publish(
            topic=Topics.DEPLOYMENT_EVENTS,
            event_type="deployment.started",
            tenant_id=deployment.tenant_id,
            payload=payload,
            user_id=_SYSTEM_USER,
        )
    except Exception as exc:
        logger.warning("Failed to emit deployment.started for %s: %s", deployment.id, exc)
        return ""


async def emit_deployment_completed(deployment: "Deployment") -> str:
    """Emit deployment.completed when gateway reports SUCCESS."""
    payload = {**_deployment_payload(deployment), "spec_hash": deployment.spec_hash}
    try:
        return await kafka_service.publish(
            topic=Topics.DEPLOYMENT_EVENTS,
            event_type="deployment.completed",
            tenant_id=deployment.tenant_id,
            payload=payload,
            user_id=_SYSTEM_USER,
        )
    except Exception as exc:
        logger.warning("Failed to emit deployment.completed for %s: %s", deployment.id, exc)
        return ""


async def emit_deployment_failed(deployment: "Deployment") -> str:
    """Emit deployment.failed when gateway reports FAILED."""
    payload = {**_deployment_payload(deployment), "error_message": deployment.error_message}
    try:
        return await kafka_service.publish(
            topic=Topics.DEPLOYMENT_EVENTS,
            event_type="deployment.failed",
            tenant_id=deployment.tenant_id,
            payload=payload,
            user_id=_SYSTEM_USER,
        )
    except Exception as exc:
        logger.warning("Failed to emit deployment.failed for %s: %s", deployment.id, exc)
        return ""


async def emit_deployment_rolledback(deployment: "Deployment") -> str:
    """Emit deployment.rolledback when a rollback deployment completes."""
    payload = {
        **_deployment_payload(deployment),
        "rollback_version": deployment.rollback_version,
    }
    try:
        return await kafka_service.publish(
            topic=Topics.DEPLOYMENT_EVENTS,
            event_type="deployment.rolledback",
            tenant_id=deployment.tenant_id,
            payload=payload,
            user_id=_SYSTEM_USER,
        )
    except Exception as exc:
        logger.warning("Failed to emit deployment.rolledback for %s: %s", deployment.id, exc)
        return ""
