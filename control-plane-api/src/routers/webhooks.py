"""Webhooks router - GitLab webhook handlers for GitOps with full tracing"""
import hmac
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from ..config import settings
from ..services.kafka_service import kafka_service, Topics
from ..models.traces import PipelineTrace, trace_store, TraceStatus

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
):
    """
    Handle GitLab webhooks for GitOps with full pipeline tracing.
    """
    # Create trace for this webhook
    event_type = x_gitlab_event or "Unknown"
    body = await request.json()

    trace = PipelineTrace(
        trigger_type=f"gitlab-{event_type.lower().replace(' hook', '').replace(' ', '-')}",
        trigger_source="gitlab",
    )
    trace.start()

    # Step 1: Webhook Reception
    step_receive = trace.add_step("webhook_received")
    step_receive.start()

    try:
        # Extract Git info from payload
        trace.git_project = body.get("project", {}).get("path_with_namespace") or str(body.get("project_id", ""))
        trace.git_branch = body.get("ref", "").replace("refs/heads/", "").replace("refs/tags/", "")

        if body.get("commits"):
            last_commit = body["commits"][-1] if body["commits"] else {}
            trace.git_commit_sha = body.get("after") or last_commit.get("id")
            trace.git_commit_message = last_commit.get("message", "").strip()[:200]
            author = last_commit.get("author", {})
            trace.git_author = author.get("name") or body.get("user_name", "unknown")
            trace.git_author_email = author.get("email") or body.get("user_email")

            # Collect all changed files
            all_files = []
            for commit in body.get("commits", []):
                all_files.extend(commit.get("added", []))
                all_files.extend(commit.get("modified", []))
                all_files.extend(commit.get("removed", []))
            trace.git_files_changed = list(set(all_files))[:50]  # Limit to 50 files
        else:
            trace.git_author = body.get("user_name") or body.get("user_username", "unknown")

        step_receive.complete({
            "event_type": event_type,
            "project": trace.git_project,
            "branch": trace.git_branch,
            "author": trace.git_author,
            "commit": trace.git_commit_sha[:8] if trace.git_commit_sha else None,
        })

        # Step 2: Token Verification
        step_auth = trace.add_step("token_verification")
        step_auth.start()

        webhook_secret = getattr(settings, 'GITLAB_WEBHOOK_SECRET', '')
        if webhook_secret and not verify_gitlab_token(x_gitlab_token, webhook_secret):
            step_auth.fail("Invalid webhook token")
            trace.fail("Authentication failed: Invalid webhook token")
            trace_store.save(trace)
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        step_auth.complete({"verified": True})

        # Step 3: Event Processing
        step_process = trace.add_step("event_processing")
        step_process.start()

        if event_type == "Push Hook":
            result = await handle_push_event_traced(body, trace)
            step_process.complete(result)
        elif event_type == "Merge Request Hook":
            result = await handle_merge_request_event_traced(body, trace)
            step_process.complete(result)
        elif event_type == "Tag Push Hook":
            result = await handle_tag_push_event_traced(body, trace)
            step_process.complete(result)
        else:
            step_process.complete({"action": "ignored", "reason": f"Unsupported event: {event_type}"})
            trace.status = TraceStatus.SKIPPED
            trace_store.save(trace)
            return {"status": "ignored", "event": event_type, "trace_id": trace.id}

        # Pipeline complete
        trace.complete()
        trace_store.save(trace)

        logger.info(f"Pipeline trace {trace.id}: {trace.status.value} in {trace.total_duration_ms}ms")

        return {
            "status": "processed",
            "event": event_type,
            "trace_id": trace.id,
            "duration_ms": trace.total_duration_ms,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing GitLab webhook: {e}", exc_info=True)

        # Mark current step as failed
        for step in trace.steps:
            if step.status == TraceStatus.IN_PROGRESS:
                step.fail(str(e))
                break

        trace.fail(str(e))
        trace_store.save(trace)

        raise HTTPException(status_code=500, detail=str(e))


async def handle_push_event_traced(payload: dict, trace: PipelineTrace) -> dict:
    """Handle push events with full tracing."""
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    commits = payload.get("commits", [])
    user_name = payload.get("user_username", "unknown")

    # Check branch
    if branch not in ("main", "master"):
        return {"action": "skipped", "reason": f"Non-main branch: {branch}"}

    # Step: Analyze Changes
    step_analyze = trace.add_step("analyze_changes")
    step_analyze.start()

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

    step_analyze.complete({
        "files_analyzed": sum(len(c.get("added", []) + c.get("modified", [])) for c in commits),
        "apis_affected": len(affected_apis),
        "apis": [f"{t}/{a}" for t, a in affected_apis],
        "mcp_servers_affected": len(affected_mcp_servers),
        "mcp_servers": [f"{s}/{n}" for t, n, s in affected_mcp_servers],
    })

    if not affected_apis and not affected_mcp_servers:
        return {"action": "skipped", "reason": "No API or MCP server changes detected"}

    # Update trace with first affected API
    if affected_apis:
        first_api = list(affected_apis)[0]
        trace.tenant_id = first_api[0]
        trace.api_name = first_api[1]
        trace.environment = "dev"

    # Step: Publish to Kafka
    step_kafka = trace.add_step("kafka_publish")
    step_kafka.start()

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
                    "trace_id": trace.id,  # Link trace ID
                },
                user_id=user_name
            )
            events_published.append({
                "event_id": event_id,
                "tenant_id": tenant_id,
                "api_name": api_name,
            })

        step_kafka.complete({
            "topic": Topics.DEPLOY_REQUESTS,
            "events_count": len(events_published),
            "events": events_published,
        })

    except Exception as e:
        step_kafka.fail(str(e))
        raise

    # Step: AWX Trigger (will be updated by deployment worker)
    step_awx = trace.add_step("awx_trigger")
    step_awx.status = TraceStatus.PENDING
    step_awx.details = {"note": "Awaiting deployment worker"}

    # Step: Publish MCP server events
    mcp_events_published = []
    if affected_mcp_servers:
        step_mcp = trace.add_step("mcp_server_sync")
        step_mcp.start()

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

            step_mcp.complete({
                "topic": Topics.MCP_SERVER_EVENTS,
                "events_count": len(mcp_events_published),
                "events": mcp_events_published,
            })

        except Exception as e:
            step_mcp.fail(str(e))
            logger.error(f"Failed to publish MCP server events: {e}")
            # Don't raise - MCP sync failure shouldn't block API deployments

    return {
        "action": "deployed",
        "apis_count": len(affected_apis),
        "events_published": len(events_published),
        "mcp_servers_count": len(affected_mcp_servers),
        "mcp_events_published": len(mcp_events_published),
    }


async def handle_merge_request_event_traced(payload: dict, trace: PipelineTrace) -> dict:
    """Handle merge request events with tracing."""
    object_attrs = payload.get("object_attributes", {})
    action = object_attrs.get("action")
    state = object_attrs.get("state")
    target_branch = object_attrs.get("target_branch")

    trace.git_branch = target_branch

    if state != "merged" or target_branch not in ("main", "master"):
        return {"action": "skipped", "reason": f"MR state={state}, target={target_branch}"}

    user = payload.get("user", {})
    user_name = user.get("username", "unknown")
    mr_iid = object_attrs.get("iid")
    title = object_attrs.get("title", "")

    trace.git_commit_message = f"MR !{mr_iid}: {title}"

    # Step: Publish sync request
    step_kafka = trace.add_step("kafka_publish")
    step_kafka.start()

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

        step_kafka.complete({
            "topic": Topics.DEPLOY_REQUESTS,
            "event_id": event_id,
            "mr_iid": mr_iid,
        })

    except Exception as e:
        step_kafka.fail(str(e))
        raise

    return {"action": "sync_triggered", "mr_iid": mr_iid}


async def handle_tag_push_event_traced(payload: dict, trace: PipelineTrace) -> dict:
    """Handle tag push events with tracing."""
    ref = payload.get("ref", "")
    tag_name = ref.replace("refs/tags/", "")
    user_name = payload.get("user_username", "unknown")

    trace.git_branch = f"tag:{tag_name}"

    # For now, just log it
    return {"action": "logged", "tag": tag_name, "note": "Tag events not yet implemented"}


# Health check for webhook endpoint
@router.get("/gitlab/health")
async def webhook_health():
    """Health check for GitLab webhook endpoint"""
    stats = trace_store.get_stats()
    return {
        "status": "healthy",
        "endpoint": "/webhooks/gitlab",
        "supported_events": ["Push Hook", "Merge Request Hook", "Tag Push Hook"],
        "trace_stats": stats,
    }
