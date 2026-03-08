"""Slack message templates for deployment + promotion lifecycle events.

Deployment events (CAB-1413): deployment.started, deployment.completed,
deployment.failed, deployment.rolledback.

Promotion events (CAB-1706): promotion.pending_approval, promotion.approved,
promotion.completed, promotion.rolled_back.
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


def promotion_pending_approval(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    source = payload.get("source_environment", "?").upper()
    target = payload.get("target_environment", "?").upper()
    requester = payload.get("requested_by", "unknown")
    message = payload.get("message", "")
    tenant = payload.get("tenant_id", "unknown")
    is_prod = payload.get("target_environment", "") == "production"
    eyes = "4-eyes required — a different user must approve" if is_prod else "self-approval allowed"
    console_url = payload.get("console_url", "")
    link = f"\n  → <{console_url}/promotions|Review in Console>" if console_url else ""
    return (
        f":eyes: *Promotion awaiting approval*\n"
        f"  *{api}* {source} → {target} | Tenant: {tenant}\n"
        f"  Requested by: {requester} | _{eyes}_"
        + (f"\n  Message: _{message}_" if message else "")
        + link
    )


def promotion_approved(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    source = payload.get("source_environment", "?").upper()
    target = payload.get("target_environment", "?").upper()
    approved_by = payload.get("approved_by", "unknown")
    return (
        f":white_check_mark: *Promotion approved*\n"
        f"  *{api}* {source} → {target} | Approved by: {approved_by}"
    )


def promotion_rolled_back(payload: dict[str, Any]) -> str:
    api = payload.get("api_name", payload.get("api_id", "unknown"))
    source = payload.get("source_environment", "?").upper()
    target = payload.get("target_environment", "?").upper()
    requester = payload.get("requested_by", "unknown")
    return (
        f":arrows_counterclockwise: *Promotion rolled back*\n"
        f"  *{api}* {source} → {target} | By: {requester}"
    )


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
        case "promotion.pending_approval":
            return promotion_pending_approval(payload)
        case "promotion.approved":
            return promotion_approved(payload)
        case "promotion.rolled_back":
            return promotion_rolled_back(payload)
        case _:
            return None
