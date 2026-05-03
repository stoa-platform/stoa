"""Canonical API lifecycle router."""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import (
    Permission,
    User,
    get_current_user,
    require_permission,
    require_tenant_access,
    require_writable_environment,
)
from src.database import get_db
from src.schemas.api_lifecycle import (
    ApiLifecycleCreateDraftRequest,
    ApiLifecycleDeployRequest,
    ApiLifecycleDeployResponse,
    ApiLifecyclePromoteRequest,
    ApiLifecyclePromotionRequestResponse,
    ApiLifecyclePublishRequest,
    ApiLifecyclePublishResponse,
    ApiLifecycleStateResponse,
    ApiLifecycleValidateDraftRequest,
    ApiLifecycleValidateDraftResponse,
)
from src.services.api_lifecycle import (
    ApiLifecycleService,
    SqlAlchemyApiLifecycleRepository,
    SqlAlchemyLifecycleAuditSink,
)
from src.services.api_lifecycle.errors import (
    ApiLifecycleConflictError,
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleSpecValidationError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    CreateApiDraftCommand,
    DeployApiCommand,
    LifecycleActor,
    PromoteApiCommand,
    PublishApiCommand,
    ValidateApiDraftCommand,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/apis", tags=["API Lifecycle"])


def _build_service(db: AsyncSession) -> ApiLifecycleService:
    return ApiLifecycleService(
        repository=SqlAlchemyApiLifecycleRepository(db),
        audit_sink=SqlAlchemyLifecycleAuditSink(db),
    )


def _actor_from_user(user: User) -> LifecycleActor:
    return LifecycleActor(
        actor_id=getattr(user, "id", None),
        email=getattr(user, "email", None),
        username=getattr(user, "username", None),
    )


def _response_from_state(state) -> ApiLifecycleStateResponse:
    return ApiLifecycleStateResponse.model_validate(asdict(state))


def _response_from_validation(outcome) -> ApiLifecycleValidateDraftResponse:
    payload = asdict(outcome)
    payload["lifecycle"] = payload.pop("lifecycle_state")
    return ApiLifecycleValidateDraftResponse.model_validate(payload)


def _response_from_deployment(outcome) -> ApiLifecycleDeployResponse:
    payload = asdict(outcome)
    payload["lifecycle"] = payload.pop("lifecycle_state")
    return ApiLifecycleDeployResponse.model_validate(payload)


def _response_from_publication(outcome) -> ApiLifecyclePublishResponse:
    payload = asdict(outcome)
    payload["lifecycle"] = payload.pop("lifecycle_state")
    return ApiLifecyclePublishResponse.model_validate(payload)


def _response_from_promotion(outcome) -> ApiLifecyclePromotionRequestResponse:
    payload = asdict(outcome)
    payload["lifecycle"] = payload.pop("lifecycle_state")
    return ApiLifecyclePromotionRequestResponse.model_validate(payload)


@router.post(
    "/lifecycle/drafts",
    response_model=ApiLifecycleStateResponse,
    status_code=201,
    dependencies=[Depends(require_writable_environment)],
)
@require_permission(Permission.APIS_CREATE)
@require_tenant_access
async def create_api_draft(
    tenant_id: str,
    request: ApiLifecycleCreateDraftRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an API draft through the canonical lifecycle service."""
    service = _build_service(db)
    try:
        state = await service.create_draft(
            CreateApiDraftCommand(
                tenant_id=tenant_id,
                name=request.name,
                display_name=request.display_name,
                version=request.version,
                description=request.description,
                backend_url=request.backend_url,
                openapi_spec=request.openapi_spec,
                spec_reference=request.spec_reference,
                tags=tuple(request.tags),
                owner_team=request.owner_team,
            ),
            actor=_actor_from_user(user),
        )
        await db.commit()
        return _response_from_state(state)
    except ApiLifecycleValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApiLifecycleConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to create API lifecycle draft for tenant=%s", tenant_id)
        raise HTTPException(status_code=500, detail="Failed to create API draft") from exc


@router.post("/{api_id}/lifecycle/validate", response_model=ApiLifecycleValidateDraftResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def validate_api_draft(
    tenant_id: str,
    api_id: str,
    request: ApiLifecycleValidateDraftRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a draft API and transition its catalog status to ready."""
    service = _build_service(db)
    try:
        outcome = await service.validate_draft(
            ValidateApiDraftCommand(
                tenant_id=tenant_id,
                api_id=api_id,
                reason=request.reason if request else None,
            ),
            actor=_actor_from_user(user),
        )
        await db.commit()
        return _response_from_validation(outcome)
    except ApiLifecycleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApiLifecycleTransitionError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleSpecValidationError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to validate API lifecycle draft for tenant=%s api_id=%s", tenant_id, api_id)
        raise HTTPException(status_code=500, detail="Failed to validate API draft") from exc


@router.post("/{api_id}/lifecycle/deployments", response_model=ApiLifecycleDeployResponse)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def deploy_api_to_lifecycle_gateway(
    tenant_id: str,
    api_id: str,
    request: ApiLifecycleDeployRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a runtime deployment by creating/updating GatewayDeployment."""
    service = _build_service(db)
    try:
        outcome = await service.deploy_to_environment(
            DeployApiCommand(
                tenant_id=tenant_id,
                api_id=api_id,
                environment=request.environment,
                gateway_instance_id=request.gateway_instance_id,
                force=request.force,
            ),
            actor=_actor_from_user(user),
        )
        await db.commit()
        return _response_from_deployment(outcome)
    except (ApiLifecycleNotFoundError, ApiLifecycleGatewayNotFoundError) as exc:
        await db.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApiLifecycleTransitionError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleGatewayAmbiguousError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleValidationError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to deploy API lifecycle target for tenant=%s api_id=%s", tenant_id, api_id)
        raise HTTPException(status_code=500, detail="Failed to request API deployment") from exc


@router.post("/{api_id}/lifecycle/publications", response_model=ApiLifecyclePublishResponse)
@require_permission(Permission.APIS_UPDATE)
@require_tenant_access
async def publish_api_to_lifecycle_portal(
    tenant_id: str,
    api_id: str,
    request: ApiLifecyclePublishRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a synced GatewayDeployment to the STOA portal catalog."""
    service = _build_service(db)
    try:
        outcome = await service.publish_to_portal(
            PublishApiCommand(
                tenant_id=tenant_id,
                api_id=api_id,
                environment=request.environment,
                gateway_instance_id=request.gateway_instance_id,
                force=request.force,
            ),
            actor=_actor_from_user(user),
        )
        await db.commit()
        return _response_from_publication(outcome)
    except (ApiLifecycleNotFoundError, ApiLifecycleGatewayNotFoundError) as exc:
        await db.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApiLifecycleTransitionError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleGatewayAmbiguousError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleSpecValidationError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    except ApiLifecycleValidationError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to publish API lifecycle target for tenant=%s api_id=%s", tenant_id, api_id)
        raise HTTPException(status_code=500, detail="Failed to publish API") from exc


@router.post("/{api_id}/lifecycle/promotions", response_model=ApiLifecyclePromotionRequestResponse)
@require_permission(Permission.APIS_DEPLOY)
@require_tenant_access
async def promote_api_through_lifecycle(
    tenant_id: str,
    api_id: str,
    request: ApiLifecyclePromoteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a controlled cross-environment API promotion."""
    service = _build_service(db)
    try:
        outcome = await service.promote_to_environment(
            PromoteApiCommand(
                tenant_id=tenant_id,
                api_id=api_id,
                source_environment=request.source_environment,
                target_environment=request.target_environment,
                source_gateway_instance_id=request.source_gateway_instance_id,
                target_gateway_instance_id=request.target_gateway_instance_id,
                force=request.force,
            ),
            actor=_actor_from_user(user),
        )
        await db.commit()
        return _response_from_promotion(outcome)
    except (ApiLifecycleNotFoundError, ApiLifecycleGatewayNotFoundError) as exc:
        await db.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApiLifecycleTransitionError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleGatewayAmbiguousError as exc:
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiLifecycleValidationError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to promote API lifecycle target for tenant=%s api_id=%s", tenant_id, api_id)
        raise HTTPException(status_code=500, detail="Failed to promote API") from exc


@router.get("/{api_id}/lifecycle", response_model=ApiLifecycleStateResponse)
@require_permission(Permission.APIS_READ)
@require_tenant_access
async def get_api_lifecycle_state(
    tenant_id: str,
    api_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the aggregate lifecycle state calculated from catalog, gateway, and promotion state."""
    service = _build_service(db)
    try:
        state = await service.get_lifecycle_state(tenant_id, api_id)
        return _response_from_state(state)
    except ApiLifecycleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to load API lifecycle state for tenant=%s api_id=%s", tenant_id, api_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve API lifecycle state") from exc
