"""Deployments router - API deployment management"""
import uuid
from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..services.git_service import git_service
from ..services.kafka_service import Topics, kafka_service

router = APIRouter(prefix="/v1/tenants/{tenant_id}/deployments", tags=["Deployments"])

class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"

class DeploymentStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class DeploymentRequest(BaseModel):
    api_id: str
    environment: Environment
    version: str | None = None  # If None, deploy latest

class DeploymentResponse(BaseModel):
    id: str
    tenant_id: str
    api_id: str
    api_name: str
    environment: Environment
    version: str
    status: DeploymentStatus
    started_at: str
    completed_at: str | None = None
    deployed_by: str
    error_message: str | None = None

class RollbackRequest(BaseModel):
    target_version: str | None = None  # If None, rollback to previous

@router.get("", response_model=list[DeploymentResponse])
@require_tenant_access
async def list_deployments(
    tenant_id: str,
    api_id: str | None = None,
    environment: Environment | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user)
):
    """List deployment history"""
    # TODO: Implement with database/GitLab
    return []

@router.get("/{deployment_id}", response_model=DeploymentResponse)
@require_tenant_access
async def get_deployment(
    tenant_id: str, deployment_id: str, user: User = Depends(get_current_user)
):
    """Get deployment details"""
    # TODO: Implement
    raise HTTPException(status_code=404, detail="Deployment not found")

@router.post("", response_model=DeploymentResponse)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def create_deployment(
    tenant_id: str, request: DeploymentRequest, user: User = Depends(get_current_user)
):
    """
    Deploy an API to an environment.

    This will:
    1. Validate the API exists and is deployable
    2. Create a deploy-request event in Kafka
    3. Gateway adapter will process the deployment
    4. Status updates will be streamed via SSE
    """
    # Generate deployment ID
    deployment_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    # Get API info from GitLab
    api_info = None
    api_name = request.api_id  # Default to api_id
    version = request.version or "1.0.0"
    backend_url = ""
    openapi_spec = None

    try:
        # Try to get API details from GitLab
        api_info = await git_service.get_api(tenant_id, request.api_id)
        if api_info:
            api_name = api_info.get("name", request.api_id)
            version = request.version or api_info.get("version", "1.0.0")
            backend_url = api_info.get("backend_url", "")

        # Get OpenAPI spec
        openapi_spec = await git_service.get_file(
            f"tenants/{tenant_id}/apis/{request.api_id}/openapi.yaml"
        )
    except Exception:
        # GitLab might not be configured yet, continue without it
        pass

    # Emit deploy-request to Kafka
    await kafka_service.publish(
        topic=Topics.DEPLOY_REQUESTS,
        event_type="deploy-request",
        tenant_id=tenant_id,
        payload={
            "deployment_id": deployment_id,
            "api_id": request.api_id,
            "api_name": api_name,
            "environment": request.environment.value,
            "version": version,
            "backend_url": backend_url,
            "openapi_spec": openapi_spec,
            "requested_by": user.username,
        },
        user_id=user.id
    )

    # Also emit audit event
    await kafka_service.emit_audit_event(
        tenant_id=tenant_id,
        action="create_deployment",
        resource_type="deployment",
        resource_id=deployment_id,
        user_id=user.id,
        details={
            "api_id": request.api_id,
            "environment": request.environment.value,
            "version": version,
        }
    )

    return DeploymentResponse(
        id=deployment_id,
        tenant_id=tenant_id,
        api_id=request.api_id,
        api_name=api_name,
        environment=request.environment,
        version=version,
        status=DeploymentStatus.PENDING,
        started_at=now,
        deployed_by=user.username,
    )

@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def rollback_deployment(
    tenant_id: str,
    deployment_id: str,
    request: RollbackRequest,
    user: User = Depends(get_current_user)
):
    """Rollback a deployment to a previous version"""
    rollback_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    # Emit rollback-request to Kafka
    await kafka_service.publish(
        topic=Topics.DEPLOY_REQUESTS,
        event_type="rollback-request",
        tenant_id=tenant_id,
        payload={
            "rollback_id": rollback_id,
            "original_deployment_id": deployment_id,
            "target_version": request.target_version,
            "requested_by": user.username,
        },
        user_id=user.id
    )

    # Emit audit event
    await kafka_service.emit_audit_event(
        tenant_id=tenant_id,
        action="rollback_deployment",
        resource_type="deployment",
        resource_id=deployment_id,
        user_id=user.id,
        details={
            "rollback_id": rollback_id,
            "target_version": request.target_version,
        }
    )

    return DeploymentResponse(
        id=rollback_id,
        tenant_id=tenant_id,
        api_id="",  # Will be filled from original deployment
        api_name="",
        environment=Environment.DEV,  # Will be determined
        version=request.target_version or "previous",
        status=DeploymentStatus.PENDING,
        started_at=now,
        deployed_by=user.username,
    )

@router.get("/{deployment_id}/logs")
@require_tenant_access
async def get_deployment_logs(
    tenant_id: str, deployment_id: str, user: User = Depends(get_current_user)
):
    """Get deployment logs"""
    # TODO: Implement with gateway adapter service
    return {"logs": []}

# Environment status endpoints
@router.get("/environments/{environment}/status")
@require_tenant_access
async def get_environment_status(
    tenant_id: str, environment: Environment, user: User = Depends(get_current_user)
):
    """Get status of all APIs deployed in an environment"""
    # TODO: Implement with webMethods health check
    return {
        "environment": environment,
        "healthy": True,
        "apis": []
    }
