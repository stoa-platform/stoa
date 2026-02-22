"""Slack message templates for deployment lifecycle events (CAB-1413).

Event types: deployment.started, deployment.completed, deployment.failed,
deployment.rolledback.
"""

from typing import Any


def _tenant_env(payload: dict[str, Any]) -> str:
    tenant = payload.get("tenant_id", "unknown")
    env = payload.get("environment", "unknown").upper()
    return f"Tenant: {tenant} | Env: {env}"


def deploy_started(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    version = payload.get("version", "?")
    env = payload.get("environment", "unknown")
    user = payload.get("deployed_by", "system")
    return f":rocket: Deploying *{api}* v{version} → *{env}*\n" f"  {_tenant_env(payload)} | Started by: {user}"


def rollback_started(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    env = payload.get("environment", "unknown")
    user = payload.get("deployed_by", "system")
    rollback_of = payload.get("rollback_of", "")
    return (
        f":arrows_counterclockwise: Rolling back *{api}* → *{env}*\n"
        f"  {_tenant_env(payload)} | Initiated by: {user}"
        + (f" | Reverting: `{rollback_of[:8]}`" if rollback_of else "")
    )


def deploy_completed(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    version = payload.get("version", "?")
    return f":white_check_mark: *{api}* v{version} deployed successfully\n" f"  {_tenant_env(payload)}"


def deploy_failed(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    version = payload.get("version", "?")
    error = payload.get("error_message") or "unknown error"
    deployment_id = payload.get("deployment_id", "")
    hint = f"`stoa logs {api}`" if api and api != "unknown" else "`stoa deploy list`"
    return (
        f":x: *{api}* v{version} FAILED — {error}\n"
        f"  {_tenant_env(payload)}\n"
        + (f"  Deployment: `{deployment_id[:8]}`\n" if deployment_id else "")
        + f"  → Run: {hint}"
    )


def deploy_rolledback(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    rollback_version = payload.get("rollback_version") or payload.get("version", "?")
    return f":white_check_mark: *{api}* rolled back to v{rollback_version}\n" f"  {_tenant_env(payload)}"


def format_message(event_type: str, payload: dict[str, Any]) -> str | None:
    """Return a formatted Slack message string for the given event type.

    Returns None if the event type is unrecognised (skip silently).
    """
    is_rollback = bool(payload.get("rollback_of"))

    match event_type:
        case "deployment.started":
            return rollback_started(payload) if is_rollback else deploy_started(payload)
        case "deployment.completed":
            return deploy_completed(payload)
        case "deployment.failed":
            return deploy_failed(payload)
        case "deployment.rolledback":
            return deploy_rolledback(payload)
        case _:
            return None
