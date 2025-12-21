"""Webhooks router - GitLab webhook handlers for GitOps"""
import hmac
import hashlib
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from ..config import settings
from ..services.kafka_service import kafka_service, Topics

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
    Handle GitLab webhooks for GitOps.

    Supported events:
    - Push Event: Triggers deployment when changes are pushed to main branch
    - Merge Request Event: Can trigger deployments when MRs are merged

    Configure in GitLab:
    Project → Settings → Webhooks → Add webhook
    URL: https://api.dev.apim.cab-i.com/webhooks/gitlab
    Secret Token: <GITLAB_WEBHOOK_SECRET>
    Trigger: Push events, Merge request events
    """
    # Verify webhook token
    webhook_secret = getattr(settings, 'GITLAB_WEBHOOK_SECRET', '')
    if webhook_secret and not verify_gitlab_token(x_gitlab_token, webhook_secret):
        logger.warning("Invalid GitLab webhook token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    # Parse event type
    event_type = x_gitlab_event or "Unknown"
    body = await request.json()

    logger.info(f"Received GitLab webhook: {event_type}")

    try:
        if event_type == "Push Hook":
            await handle_push_event(body)
        elif event_type == "Merge Request Hook":
            await handle_merge_request_event(body)
        elif event_type == "Tag Push Hook":
            await handle_tag_push_event(body)
        else:
            logger.info(f"Ignoring unsupported event type: {event_type}")
            return {"status": "ignored", "event": event_type}

        return {"status": "processed", "event": event_type}

    except Exception as e:
        logger.error(f"Error processing GitLab webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def handle_push_event(payload: dict):
    """
    Handle push events from GitLab.

    When changes are pushed to main branch, analyze the changed files
    and trigger deployments for affected APIs.
    """
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    commits = payload.get("commits", [])
    project_id = payload.get("project_id")
    user_name = payload.get("user_username", "unknown")

    logger.info(f"Push to {branch} by {user_name}: {len(commits)} commits")

    # Only process pushes to main/master
    if branch not in ("main", "master"):
        logger.info(f"Ignoring push to non-main branch: {branch}")
        return

    # Analyze changed files to find affected APIs
    affected_apis = set()
    for commit in commits:
        for file_path in commit.get("added", []) + commit.get("modified", []):
            # Parse tenant and API from path: tenants/{tenant_id}/apis/{api_name}/...
            parts = file_path.split("/")
            if len(parts) >= 4 and parts[0] == "tenants" and parts[2] == "apis":
                tenant_id = parts[1]
                api_name = parts[3]
                affected_apis.add((tenant_id, api_name))

    logger.info(f"Affected APIs: {affected_apis}")

    # Emit deploy requests for each affected API
    for tenant_id, api_name in affected_apis:
        await kafka_service.publish(
            topic=Topics.DEPLOY_REQUESTS,
            event_type="deploy-request",
            tenant_id=tenant_id,
            payload={
                "api_name": api_name,
                "api_id": api_name,  # Use name as ID for now
                "environment": "dev",  # Default to dev
                "version": payload.get("after", "")[:8],  # Use commit SHA as version
                "trigger": "gitlab-push",
                "commit_sha": payload.get("after"),
                "commit_message": commits[-1].get("message", "") if commits else "",
                "requested_by": user_name,
            },
            user_id=user_name
        )
        logger.info(f"Emitted deploy-request for {tenant_id}/{api_name}")


async def handle_merge_request_event(payload: dict):
    """
    Handle merge request events from GitLab.

    When an MR is merged to main, trigger deployments for affected APIs.
    """
    object_attrs = payload.get("object_attributes", {})
    action = object_attrs.get("action")  # open, close, merge, update, etc.
    state = object_attrs.get("state")  # opened, closed, merged
    target_branch = object_attrs.get("target_branch")

    logger.info(f"MR event: action={action}, state={state}, target={target_branch}")

    # Only process merged MRs to main
    if state != "merged" or target_branch not in ("main", "master"):
        logger.info(f"Ignoring MR event: state={state}, target={target_branch}")
        return

    # Get MR info
    user = payload.get("user", {})
    user_name = user.get("username", "unknown")
    mr_iid = object_attrs.get("iid")
    title = object_attrs.get("title", "")

    # Emit sync event to refresh gateway state
    # The specific API changes are handled by the push event that follows the merge
    await kafka_service.publish(
        topic=Topics.DEPLOY_REQUESTS,
        event_type="sync-request",
        tenant_id="all",  # Apply to all tenants
        payload={
            "trigger": "gitlab-merge",
            "mr_iid": mr_iid,
            "mr_title": title,
            "requested_by": user_name,
        },
        user_id=user_name
    )

    logger.info(f"Emitted sync-request after MR !{mr_iid} merge")


async def handle_tag_push_event(payload: dict):
    """
    Handle tag push events from GitLab.

    Tags can be used for versioned releases.
    """
    ref = payload.get("ref", "")
    tag_name = ref.replace("refs/tags/", "")
    user_name = payload.get("user_username", "unknown")

    logger.info(f"Tag {tag_name} created by {user_name}")

    # For now, just log it
    # Could trigger production deployments based on tags


# Health check for webhook endpoint
@router.get("/gitlab/health")
async def webhook_health():
    """Health check for GitLab webhook endpoint"""
    return {
        "status": "healthy",
        "endpoint": "/webhooks/gitlab",
        "supported_events": ["Push Hook", "Merge Request Hook", "Tag Push Hook"]
    }
