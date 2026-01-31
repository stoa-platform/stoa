"""
Client Certificate Provisioning Router (CAB-865)

Endpoints for creating clients with mTLS certificates.
Private key returned ONE TIME only at creation/rotation.
Rate limited: 10 requests/hour/tenant for write operations.
"""
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User, get_current_user
from src.auth.rbac import Permission, require_permission
from src.database import get_db
from src.middleware.rate_limit import limiter
from src.models.client import Client, ClientStatus
from src.schemas.client import (
    CertificateRotateRequest,
    ClientCreate,
    ClientResponse,
    ClientWithCertificate,
)
from src.services.certificate_service import CertificateServiceError, certificate_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/clients", tags=["clients"])


def _tenant_key(request: Request) -> str:
    """Rate limit key by tenant_id for client cert operations."""
    user = getattr(request.state, "user", None)
    tenant_id = getattr(user, "tenant_id", "unknown") if user else "unknown"
    return f"clients:{tenant_id}"


@router.post(
    "",
    response_model=ClientWithCertificate,
    status_code=status.HTTP_201_CREATED,
    summary="Create client with mTLS certificate",
)
@require_permission(Permission.CLIENTS_WRITE)
@limiter.limit("10/hour", key_func=_tenant_key)
async def create_client(
    request: Request,
    body: ClientCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new client and generate an mTLS certificate.

    The private key is returned ONE TIME in this response.
    It is never stored and cannot be retrieved again.
    """
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    # Generate CN from name (lowercase, replace spaces)
    cn = body.name.strip().lower().replace(" ", "-")

    # Validate CN
    try:
        cn = certificate_service.validate_common_name(cn)
    except CertificateServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check CN uniqueness within tenant
    existing = await db.execute(
        select(Client).where(
            Client.tenant_id == user.tenant_id,
            Client.certificate_cn == cn,
            Client.status != ClientStatus.REVOKED,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Client with CN '{cn}' already exists in this tenant")

    # Create DB record first
    client = Client(
        tenant_id=user.tenant_id,
        name=body.name.strip(),
        certificate_cn=cn,
        status=ClientStatus.ACTIVE,
    )
    db.add(client)
    await db.flush()

    # Generate certificate
    try:
        result = await certificate_service.generate_certificate(
            common_name=cn,
            tenant_id=user.tenant_id,
            client_id=str(client.id),
        )
    except CertificateServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Update client with cert metadata
    client.certificate_serial = result.serial_number
    client.certificate_fingerprint = result.fingerprint_sha256
    client.certificate_pem = result.certificate_pem
    client.certificate_not_before = result.not_before
    client.certificate_not_after = result.not_after
    await db.flush()
    await db.refresh(client)

    return ClientWithCertificate(
        id=client.id,
        tenant_id=client.tenant_id,
        name=client.name,
        certificate_cn=client.certificate_cn,
        certificate_serial=client.certificate_serial,
        certificate_fingerprint=client.certificate_fingerprint,
        certificate_pem=client.certificate_pem,
        certificate_not_before=client.certificate_not_before,
        certificate_not_after=client.certificate_not_after,
        status=client.status,
        created_at=client.created_at,
        updated_at=client.updated_at,
        private_key_pem=result.private_key_pem,
    )


@router.get(
    "",
    response_model=List[ClientResponse],
    summary="List clients for current tenant",
)
@require_permission(Permission.CLIENTS_READ)
async def list_clients(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all clients for the authenticated user's tenant."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    result = await db.execute(
        select(Client)
        .where(Client.tenant_id == user.tenant_id)
        .order_by(Client.created_at.desc())
    )
    clients = result.scalars().all()
    return [ClientResponse.model_validate(c) for c in clients]


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Get client details",
)
@require_permission(Permission.CLIENTS_READ)
async def get_client(
    client_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get client details. Private key is never returned here."""
    client = await _get_client_for_tenant(client_id, user, db)
    return ClientResponse.model_validate(client)


@router.post(
    "/{client_id}/rotate",
    response_model=ClientWithCertificate,
    summary="Rotate client certificate",
)
@require_permission(Permission.CLIENTS_WRITE)
@limiter.limit("10/hour", key_func=_tenant_key)
async def rotate_certificate(
    request: Request,
    client_id: UUID,
    body: CertificateRotateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rotate a client's certificate. Returns new private key ONE TIME."""
    client = await _get_client_for_tenant(client_id, user, db)

    if client.status != ClientStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Cannot rotate certificate for non-active client")

    old_serial = client.certificate_serial
    try:
        result = await certificate_service.rotate_certificate(
            client_id=str(client.id),
            tenant_id=client.tenant_id,
            common_name=client.certificate_cn,
            old_serial=old_serial or "",
        )
    except CertificateServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))

    client.certificate_serial = result.serial_number
    client.certificate_fingerprint = result.fingerprint_sha256
    client.certificate_pem = result.certificate_pem
    client.certificate_not_before = result.not_before
    client.certificate_not_after = result.not_after
    await db.flush()
    await db.refresh(client)

    return ClientWithCertificate(
        id=client.id,
        tenant_id=client.tenant_id,
        name=client.name,
        certificate_cn=client.certificate_cn,
        certificate_serial=client.certificate_serial,
        certificate_fingerprint=client.certificate_fingerprint,
        certificate_pem=client.certificate_pem,
        certificate_not_before=client.certificate_not_before,
        certificate_not_after=client.certificate_not_after,
        status=client.status,
        created_at=client.created_at,
        updated_at=client.updated_at,
        private_key_pem=result.private_key_pem,
    )


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke client certificate and soft-delete",
)
@require_permission(Permission.CLIENTS_WRITE)
async def delete_client(
    client_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the client's certificate and mark as revoked (soft delete)."""
    client = await _get_client_for_tenant(client_id, user, db)

    if client.status == ClientStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Client already revoked")

    if client.certificate_serial:
        try:
            await certificate_service.revoke_certificate(
                client_id=str(client.id),
                tenant_id=client.tenant_id,
                serial_number=client.certificate_serial,
                reason="client_deleted",
            )
        except CertificateServiceError as e:
            raise HTTPException(status_code=500, detail=str(e))

    client.status = ClientStatus.REVOKED
    await db.flush()


async def _get_client_for_tenant(
    client_id: UUID, user: User, db: AsyncSession
) -> Client:
    """Fetch client with tenant isolation check."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client.tenant_id != user.tenant_id and "cpi-admin" not in user.roles:
        raise HTTPException(status_code=404, detail="Client not found")

    return client
