"""DCR onboarding API for OAuth clients with SCIM-derived roles (CAB-1483).

Endpoints:
- POST   /v1/oauth-clients/           Register a new client
- GET    /v1/oauth-clients/           List clients for tenant
- GET    /v1/oauth-clients/{id}       Get client details
- DELETE /v1/oauth-clients/{id}       Revoke a client
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..database import get_db
from ..repositories.oauth_client import OAuthClientRepository
from ..schemas.oauth_client import OAuthClientCreate, OAuthClientListResponse, OAuthClientResponse
from ..services.identity_governance import IdentityGovernanceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/oauth-clients", tags=["OAuth Clients"])


@router.post("/", response_model=OAuthClientResponse, status_code=201)
async def register_oauth_client(
    body: OAuthClientCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthClientResponse:
    """Register a new OAuth client via DCR with SCIM-derived product roles."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant_id in token")

    try:
        svc = IdentityGovernanceService(db)
        client = await svc.register_client(
            tenant_id=user.tenant_id,
            client_name=body.client_name,
            description=body.description,
            product_roles=body.product_roles,
            oauth_metadata=body.oauth_metadata,
            actor_id=user.id,
            actor_email=user.email,
        )
        await db.commit()
        return OAuthClientResponse.model_validate(client)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register OAuth client: {e}")
        raise HTTPException(status_code=503, detail="Internal error during client registration")


@router.get("/", response_model=OAuthClientListResponse)
async def list_oauth_clients(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthClientListResponse:
    """List OAuth clients for the current user's tenant."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant_id in token")

    repo = OAuthClientRepository(db)
    items, total = await repo.list_by_tenant(user.tenant_id, page=page, page_size=page_size, status=status)
    return OAuthClientListResponse(
        items=[OAuthClientResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{client_id}", response_model=OAuthClientResponse)
async def get_oauth_client(
    client_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthClientResponse:
    """Get a specific OAuth client by ID."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant_id in token")

    repo = OAuthClientRepository(db)
    client = await repo.get_by_id(client_id)
    if not client or client.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="OAuth client not found")

    return OAuthClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=204)
async def revoke_oauth_client(
    client_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke (soft-delete) an OAuth client."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant_id in token")

    svc = IdentityGovernanceService(db)
    revoked = await svc.revoke_client(
        client_id=client_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_email=user.email,
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="OAuth client not found")
    await db.commit()
