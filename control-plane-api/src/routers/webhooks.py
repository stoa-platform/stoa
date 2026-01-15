"""Webhooks router - GitLab webhook handlers for GitOps with full tracing"""
import hmac
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..services.kafka_service import kafka_service, Topics
from ..services.trace_service import TraceService
from ..models.traces_db import TraceStatusDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class GitLabPushEvent(BaseModel):
    """GitLab push webhook payload (simplified)"""
    object_kind: str  # "push"
    event_name: str  # "push"
    ref: str  # "refs/heads/main"
    before: str  # Previous commit SHA
    after: str  # New commit SHA
    checkout_sha: Optional[str] = None
    project_id: int
    user_name: str
    user_username: str
    user_email: Optional[str] = None
    commits: list = []
    total_commits_count: int = 0


class GitLabMergeRequestEvent(BaseModel):
    """GitLab merge request webhook payload (simplified)"""
    object_kind: str  # "merge_request"
    event_type: str  # "merge_request"
    user: dict
    project: dict
    object_attributes: dict


def verify_gitlab_token(token: Optional[str], expected_token: str) -> bool:
    """Verify GitLab webhook secret token"""
    if not expected_token:
        return True  # No token configured, allow all
    return hmac.compare_digest(token or "", expected_token)


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: Optional[str] = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle GitLab webhooks for GitOps with full pipeline tracing.

    Captures the git author (who pushed) from the GitLab payload and stores
    traces in PostgreSQL for persistent monitoring.
    """
    service = TraceService(db)
    event_type = x_gitlab_event or "Unknown"
    body = await request.json()

    # Extract Git info from payload
    git_project = body.get("project", {}).get("path_with_namespace") or str(body.get("project_id", ""))
    git_branch = body.get("ref", "").replace("refs/heads/", "").replace("refs/tags/", "")

    # Extract author info - this is who pushed to git
    git_commit_sha = None
    git_commit_message = None
    git_author = None
    git_author_email = None
    git_files_changed = None

    if body.get("commits"):
        last_commit = body["commits"][-1] if body["commits"] else {}
        git_commit_sha = body.get("after") or last_commit.get("id")
        git_commit_message = last_commit.get("message", "").strip()[:200]
        # Author from commit takes precedence (more accurate)
        author = last_commit.get("author", {})
        git_author = author.get("name") or body.get("user_name", "unknown")
        git_author_email = author.get("email") or body.get("user_email")

        # Collect all changed files
        all_files = []
        for commit in body.get("commits", []):
            all_files.extend(commit.get("added", []))
            all_files.extend(commit.get("modified", []))
            all_files.extend(commit.get("removed", []))
        git_files_changed = list(set(all_files))[:50]  # Limit to 50 files
    else:
        # Fallback to webhook user info
        git_author = body.get("user_name") or body.get("user_username", "unknown")
        git_author_email = body.get("user_email")

    # Create trace in PostgreSQL with full git info
    trace = await service.create(
        trigger_type=f"gitlab-{event_type.lower().replace(' hook', '').replace(' ', '-')}",
        trigger_source="gitlab",
        git_project=git_project,
        git_branch=git_branch,
        git_commit_sha=git_commit_sha,
        git_commit_message=git_commit_message,
        git_author=git_author,
        git_author_email=git_author_email,
        git_files_changed=git_files_changed,
    )

    try:
        # Step 1: Webhook Reception
        await service.add_step(
            trace,
            name="webhook_received",
            status="success",
            duration_ms=5,
            details={
                "event_type": event_type,
                "project": git_project,
                "branch": git_branch,
                "author": git_author,
                "commit": git_commit_sha[:8] if git_commit_sha else None,
            },
        )

        # Step 2: Token Verification
        webhook_secret = getattr(settings, 'GITLAB_WEBHOOK_SECRET', '')
        if webhook_secret and not verify_gitlab_token(x_gitlab_token, webhook_secret):
            await service.add_step(
                trace,
                name="token_verification",
                status="failed",
                error="Invalid webhook token",
            )
            await service.complete(trace, TraceStatusDB.FAILED, "Authentication failed: Invalid webhook token")
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        await service.add_step(
            trace,
            name="token_verification",
            status="success",
            duration_ms=2,
            details={"verified": True},
        )

        # Step 3: Event Processing
        if event_type == "Push Hook":
            result = await handle_push_event_traced_pg(body, trace, service)
        elif event_type == "Merge Request Hook":
            result = await handle_merge_request_event_traced_pg(body, trace, service)
        elif event_type == "Tag Push Hook":
            result = await handle_tag_push_event_traced_pg(body, trace, service)
        else:
            await service.add_step(
                trace,
                name="event_processing",
                status="skipped",
                details={"reason": f"Unsupported event: {event_type}"},
            )
            await service.complete(trace, TraceStatusDB.SKIPPED)
            return {"status": "ignored", "event": event_type, "trace_id": trace.id}

        await service.add_step(
            trace,
            name="event_processing",
            status="success",
            details=result,
        )

        # Pipeline complete
        await service.complete(trace, TraceStatusDB.SUCCESS)

        logger.info(f"Pipeline trace {trace.id}: {trace.status.value} in {trace.total_duration_ms}ms (author: {git_author})")

        return {
            "status": "processed",
            "event": event_type,
            "trace_id": trace.id,
            "duration_ms": trace.total_duration_ms,
            "author": git_author,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing GitLab webhook: {e}", exc_info=True)
        await service.complete(trace, TraceStatusDB.FAILED, str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def handle_push_event_traced_pg(
    payload: dict,
    trace,
    service: TraceService
) -> dict:
    """
    Handle push events with full tracing (PostgreSQL version).

    Analyzes changed files to detect API and MCP server changes,
    then publishes deployment events to Kafka.
    """
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    commits = payload.get("commits", [])
    user_name = payload.get("user_username", "unknown")

    # Check branch
    if branch not in ("main", "master"):
        return {"action": "skipped", "reason": f"Non-main branch: {branch}"}

    # Analyze changes
    affected_apis = set()
    affected_mcp_servers = set()  # (tenant_id, server_name, scope)

    for commit in commits:
        for file_path in commit.get("added", []) + commit.get("modified", []):
            parts = file_path.split("/")

            # Detect API changes: tenants/{tenant_id}/apis/{api_name}/...
            if len(parts) >= 4 and parts[0] == "tenants" and parts[2] == "apis":
                tenant_id = parts[1]
                api_name = parts[3]
                affected_apis.add((tenant_id, api_name))

            # Detect MCP server changes (tenant): tenants/{tenant_id}/mcp-servers/{server}/...
            elif len(parts) >= 5 and parts[0] == "tenants" and parts[2] == "mcp-servers":
                tenant_id = parts[1]
                server_name = parts[3]
                affected_mcp_servers.add((tenant_id, server_name, "tenant"))

            # Detect MCP server changes (platform): platform/mcp-servers/{server}/...
            elif len(parts) >= 4 and parts[0] == "platform" and parts[1] == "mcp-servers":
                server_name = parts[2]
                affected_mcp_servers.add(("_platform", server_name, "platform"))

    await service.add_step(
        trace,
        name="analyze_changes",
        status="success",
        details={
            "files_analyzed": sum(len(c.get("added", []) + c.get("modified", [])) for c in commits),
            "apis_affected": len(affected_apis),
            "apis": [f"{t}/{a}" for t, a in affected_apis],
            "mcp_servers_affected": len(affected_mcp_servers),
            "mcp_servers": [f"{s}/{n}" for t, n, s in affected_mcp_servers],
        },
    )

    if not affected_apis and not affected_mcp_servers:
        return {"action": "skipped", "reason": "No API or MCP server changes detected"}

    # Update trace with first affected API
    if affected_apis:
        first_api = list(affected_apis)[0]
        trace.tenant_id = first_api[0]
        trace.api_name = first_api[1]
        trace.environment = "dev"

    # Publish to Kafka
    events_published = []
    try:
        for tenant_id, api_name in affected_apis:
            event_id = await kafka_service.publish(
                topic=Topics.DEPLOY_REQUESTS,
                event_type="deploy-request",
                tenant_id=tenant_id,
                payload={
                    "api_name": api_name,
                    "api_id": api_name,
                    "environment": "dev",
                    "version": payload.get("after", "")[:8],
                    "trigger": "gitlab-push",
                    "commit_sha": payload.get("after"),
                    "commit_message": commits[-1].get("message", "") if commits else "",
                    "requested_by": user_name,
                    "trace_id": trace.id,
                },
                user_id=user_name
            )
            events_published.append({
                "event_id": event_id,
                "tenant_id": tenant_id,
                "api_name": api_name,
            })

        await service.add_step(
            trace,
            name="kafka_publish",
            status="success",
            details={
                "topic": Topics.DEPLOY_REQUESTS,
                "events_count": len(events_published),
                "events": events_published,
            },
        )

    except Exception as e:
        await service.add_step(
            trace,
            name="kafka_publish",
            status="failed",
            error=str(e),
        )
        raise

    # AWX Trigger step (pending, will be updated by deployment worker)
    await service.add_step(
        trace,
        name="awx_trigger",
        status="pending",
        details={"note": "Awaiting deployment worker"},
    )

    # Publish MCP server events
    mcp_events_published = []
    if affected_mcp_servers:
        try:
            for tenant_id, server_name, scope in affected_mcp_servers:
                event_id = await kafka_service.publish(
                    topic=Topics.MCP_SERVER_EVENTS,
                    event_type="mcp-server-updated",
                    tenant_id=tenant_id,
                    payload={
                        "server_name": server_name,
                        "scope": scope,
                        "trigger": "gitlab-push",
                        "commit_sha": payload.get("after"),
                        "requested_by": user_name,
                        "trace_id": trace.id,
                    },
                    user_id=user_name
                )
                mcp_events_published.append({
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "server_name": server_name,
                    "scope": scope,
                })

            await service.add_step(
                trace,
                name="mcp_server_sync",
                status="success",
                details={
                    "topic": Topics.MCP_SERVER_EVENTS,
                    "events_count": len(mcp_events_published),
                    "events": mcp_events_published,
                },
            )

        except Exception as e:
            await service.add_step(
                trace,
                name="mcp_server_sync",
                status="failed",
                error=str(e),
            )
            logger.error(f"Failed to publish MCP server events: {e}")
            # Don't raise - MCP sync failure shouldn't block API deployments

    return {
        "action": "deployed",
        "apis_count": len(affected_apis),
        "events_published": len(events_published),
        "mcp_servers_count": len(affected_mcp_servers),
        "mcp_events_published": len(mcp_events_published),
    }


async def handle_merge_request_event_traced_pg(
    payload: dict,
    trace,
    service: TraceService
) -> dict:
    """Handle merge request events with tracing (PostgreSQL version)."""
    object_attrs = payload.get("object_attributes", {})
    state = object_attrs.get("state")
    target_branch = object_attrs.get("target_branch")

    if state != "merged" or target_branch not in ("main", "master"):
        return {"action": "skipped", "reason": f"MR state={state}, target={target_branch}"}

    user = payload.get("user", {})
    user_name = user.get("username", "unknown")
    mr_iid = object_attrs.get("iid")
    title = object_attrs.get("title", "")

    try:
        event_id = await kafka_service.publish(
            topic=Topics.DEPLOY_REQUESTS,
            event_type="sync-request",
            tenant_id="all",
            payload={
                "trigger": "gitlab-merge",
                "mr_iid": mr_iid,
                "mr_title": title,
                "requested_by": user_name,
                "trace_id": trace.id,
            },
            user_id=user_name
        )

        await service.add_step(
            trace,
            name="kafka_publish",
            status="success",
            details={
                "topic": Topics.DEPLOY_REQUESTS,
                "event_id": event_id,
                "mr_iid": mr_iid,
            },
        )

    except Exception as e:
        await service.add_step(
            trace,
            name="kafka_publish",
            status="failed",
            error=str(e),
        )
        raise

    return {"action": "sync_triggered", "mr_iid": mr_iid}


async def handle_tag_push_event_traced_pg(
    payload: dict,
    trace,
    service: TraceService
) -> dict:
    """Handle tag push events with tracing (PostgreSQL version)."""
    ref = payload.get("ref", "")
    tag_name = ref.replace("refs/tags/", "")

    # For now, just log it
    return {"action": "logged", "tag": tag_name, "note": "Tag events not yet implemented"}


# Health check for webhook endpoint
@router.get("/gitlab/health")
async def webhook_health(db: AsyncSession = Depends(get_db)):
    """Health check for GitLab webhook endpoint with trace stats from PostgreSQL."""
    service = TraceService(db)
    stats = await service.get_stats()
    return {
        "status": "healthy",
        "endpoint": "/webhooks/gitlab",
        "supported_events": ["Push Hook", "Merge Request Hook", "Tag Push Hook"],
        "trace_stats": stats,
    }
