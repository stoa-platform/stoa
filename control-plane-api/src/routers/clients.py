"""
Client Router with mTLS Certificate Support

CAB-865: mTLS API Client Certificate Provisioning

Endpoints:
- POST   /v1/clients                       - Create client
- GET    /v1/clients                       - List clients
- GET    /v1/clients/{id}                  - Get client
- GET    /v1/clients/{id}/certificate      - Get cert info
- POST   /v1/clients/{id}/certificate/renew   - Renew cert
- POST   /v1/clients/{id}/certificate/revoke  - Revoke cert
- DELETE /v1/clients/{id}                  - Soft delete
"""
import logging
import math
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.auth.dependencies import get_current_user, User
from src.auth.rbac import Permission, get_user_permissions
from src.database import get_db
from src.models.client import Client, AuthType, ClientStatus
from src.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientCreateResponse,
    ClientListResponse,
    CertificateBundleResponse,
    CertificateInfoResponse,
    CertificateRevokeRequest,
    CertificateRenewResponse,
    AuthTypeEnum,
    ClientStatusEnum,
)
from src.services.certificate_service import (
    get_certificate_service,
    CertificateService,
)
from src.services.certificate_provider import (
    CertificateRequest,
    CertificateServiceUnavailable,
)
from src.events import (
    event_bus,
    EVENT_CLIENT_CREATED,
    EVENT_CLIENT_DELETED,
    EVENT_CERTIFICATE_CREATED,
    EVENT_CERTIFICATE_RENEWED,
    EVENT_CERTIFICATE_REVOKED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/clients", tags=["Clients"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in (user.roles or []):
        return True
    return user.tenant_id == tenant_id


def _check_permission(user: User, permission: str) -> None:
    """Check if user has required permission."""
    user_permissions = get_user_permissions(user.roles or [])
    if permission not in user_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission} required"
        )


# Rate limiting counter (simple in-memory, per-tenant)
# In production, use Redis or similar
_rate_limit_counter: dict = {}
RATE_LIMIT_PER_HOUR = 10


def _check_rate_limit(tenant_id: str) -> None:
    """
    Check rate limit for certificate generation.

    Security (Pr1nc3ss): Max 10 certs/hour/tenant
    """
    now = datetime.now(timezone.utc)
    hour_key = f"{tenant_id}:{now.strftime('%Y-%m-%d-%H')}"

    count = _rate_limit_counter.get(hour_key, 0)
    if count >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {RATE_LIMIT_PER_HOUR} certificates per hour"
        )

    _rate_limit_counter[hour_key] = count + 1


@router.post(
    "",
    response_model=ClientCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API client",
    description="""
    Create a new API client with optional mTLS certificate.

    **Auth Types:**
    - `oauth2`: OAuth2/OIDC only
    - `mtls`: Certificate-only authentication
    - `mtls_oauth2`: Certificate + OAuth2 (RFC 8705 certificate-bound tokens)

    For `mtls` and `mtls_oauth2`, a certificate bundle is generated.

    **IMPORTANT**: The private key is returned **ONE TIME ONLY**.
    Store it securely - it cannot be retrieved again.
    """
)
async def create_client(
    body: ClientCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new client with optional mTLS certificate."""

    # Check permission
    _check_permission(current_user, Permission.CLIENTS_CREATE)

    # Tenant from JWT only (N3m0 security - never from body)
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must have a tenant_id"
        )

    # Check for duplicate name
    result = await db.execute(
        select(Client).where(
            and_(
                Client.tenant_id == tenant_id,
                Client.name == body.name,
                Client.deleted_at.is_(None)
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Client with name '{body.name}' already exists"
        )

    # Check rate limit for mTLS
    auth_type = AuthType(body.auth_type.value)
    if auth_type in (AuthType.MTLS, AuthType.MTLS_OAUTH2):
        _check_rate_limit(tenant_id)

    # Create client
    client = Client(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        auth_type=auth_type,
        status=ClientStatus.ACTIVE,
        created_by=current_user.email or current_user.id,
    )

    # Response data
    certificate_bundle_response = None
    warnings = []

    # Generate certificate if mTLS
    if auth_type in (AuthType.MTLS, AuthType.MTLS_OAUTH2):
        try:
            cert_service = get_certificate_service()

            cert_request = CertificateRequest(
                client_id=str(client.id),
                client_name=body.name,
                tenant_id=tenant_id,
                validity_days=body.certificate_validity_days,
                key_size=body.certificate_key_size,
            )

            bundle = await cert_service.generate_certificate(cert_request)

            # Store certificate metadata (NOT private key)
            client.certificate_fingerprint_sha256 = bundle.fingerprint_sha256
            client.certificate_serial = bundle.serial_number
            client.certificate_subject = bundle.subject_dn
            client.certificate_issuer = bundle.issuer_dn
            client.certificate_valid_from = bundle.not_before
            client.certificate_valid_until = bundle.not_after
            client.vault_pki_serial = bundle.vault_pki_serial

            # Build response (includes private key - ONE TIME)
            certificate_bundle_response = CertificateBundleResponse(
                certificate_pem=bundle.certificate_pem,
                private_key_pem=bundle.private_key_pem,
                ca_chain_pem=bundle.ca_chain_pem,
                fingerprint_sha256=bundle.fingerprint_sha256,
                serial_number=bundle.serial_number,
                expires_at=bundle.not_after,
            )

            # Warn if using mock provider
            if cert_service.provider_name == "mock":
                warnings.append(
                    "Certificate generated using MOCK provider (self-signed). "
                    "Not valid for production use."
                )

        except CertificateServiceUnavailable as e:
            # Don't create client if cert generation fails
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e)
            )

    # Save to database
    db.add(client)
    await db.flush()
    await db.refresh(client)

    logger.info(
        f"Created client {client.id} ({body.name}) "
        f"auth_type={body.auth_type.value} tenant={tenant_id}"
    )

    # Publish events for CAB-866
    await event_bus.publish(EVENT_CLIENT_CREATED, {
        "client_id": str(client.id),
        "tenant_id": tenant_id,
        "name": body.name,
        "auth_type": body.auth_type.value,
    })

    if certificate_bundle_response:
        await event_bus.publish(EVENT_CERTIFICATE_CREATED, {
            "client_id": str(client.id),
            "tenant_id": tenant_id,
            "fingerprint_sha256": bundle.fingerprint_sha256,
            "serial_number": bundle.serial_number,
            "expires_at": bundle.not_after.isoformat(),
        })

    return ClientCreateResponse(
        client=ClientResponse.from_model(client),
        certificate_bundle=certificate_bundle_response,
        warnings=warnings,
    )


@router.get("", response_model=ClientListResponse)
async def list_clients(
    status: Optional[ClientStatusEnum] = None,
    auth_type: Optional[AuthTypeEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List clients for the current tenant."""

    _check_permission(current_user, Permission.CLIENTS_READ)

    tenant_id = current_user.tenant_id
    if not tenant_id and "cpi-admin" not in (current_user.roles or []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must have a tenant_id"
        )

    # Build query
    query = select(Client).where(Client.deleted_at.is_(None))

    # Filter by tenant (unless cpi-admin)
    if tenant_id:
        query = query.where(Client.tenant_id == tenant_id)

    # Filter by status
    if status:
        query = query.where(Client.status == ClientStatus(status.value))

    # Filter by auth_type
    if auth_type:
        query = query.where(Client.auth_type == AuthType(auth_type.value))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Client.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    clients = result.scalars().all()

    return ClientListResponse(
        items=[ClientResponse.from_model(c) for c in clients],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get client details."""

    _check_permission(current_user, Permission.CLIENTS_READ)

    result = await db.execute(
        select(Client).where(
            and_(
                Client.id == client_id,
                Client.deleted_at.is_(None)
            )
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Check tenant access (return 404 to avoid info leak)
    if not _has_tenant_access(current_user, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    return ClientResponse.from_model(client)


@router.get("/{client_id}/certificate", response_model=CertificateInfoResponse)
async def get_client_certificate(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get certificate metadata (no private key)."""

    _check_permission(current_user, Permission.CLIENTS_READ)

    result = await db.execute(
        select(Client).where(
            and_(
                Client.id == client_id,
                Client.deleted_at.is_(None)
            )
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not _has_tenant_access(current_user, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not client.certificate_fingerprint_sha256:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client does not have a certificate"
        )

    return CertificateInfoResponse(
        fingerprint_sha256=client.certificate_fingerprint_sha256,
        serial_number=client.certificate_serial or "",
        subject=client.certificate_subject or "",
        issuer=client.certificate_issuer or "",
        valid_from=client.certificate_valid_from,
        valid_until=client.certificate_valid_until,
        days_until_expiry=client.days_until_expiry or 0,
        is_valid=client.is_certificate_valid,
        is_revoked=client.certificate_revoked_at is not None,
        revoked_at=client.certificate_revoked_at,
        revoked_by=client.certificate_revoked_by,
        revocation_reason=client.certificate_revocation_reason,
    )


@router.post("/{client_id}/certificate/renew", response_model=CertificateRenewResponse)
async def renew_client_certificate(
    client_id: UUID,
    validity_days: int = Query(365, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Renew client certificate.

    Generates a new certificate and revokes the previous one.
    The new private key is returned ONE TIME ONLY.
    """

    _check_permission(current_user, Permission.CLIENTS_UPDATE)

    result = await db.execute(
        select(Client).where(
            and_(
                Client.id == client_id,
                Client.deleted_at.is_(None)
            )
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not _has_tenant_access(current_user, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if client.auth_type not in (AuthType.MTLS, AuthType.MTLS_OAUTH2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client does not use mTLS authentication"
        )

    # Check rate limit
    _check_rate_limit(client.tenant_id)

    # Store previous fingerprint
    previous_fingerprint = client.certificate_fingerprint_sha256

    # Revoke previous certificate
    if client.certificate_serial:
        cert_service = get_certificate_service()
        await cert_service.revoke_certificate(
            client.certificate_serial,
            reason="Certificate renewal"
        )

        client.certificate_revoked_at = datetime.now(timezone.utc)
        client.certificate_revoked_by = current_user.email or current_user.id
        client.certificate_revocation_reason = "Certificate renewal"

    # Generate new certificate
    try:
        cert_service = get_certificate_service()
        cert_request = CertificateRequest(
            client_id=str(client.id),
            client_name=client.name,
            tenant_id=client.tenant_id,
            validity_days=validity_days,
            key_size=4096,
        )

        bundle = await cert_service.generate_certificate(cert_request)

        # Update certificate metadata
        client.certificate_fingerprint_sha256 = bundle.fingerprint_sha256
        client.certificate_serial = bundle.serial_number
        client.certificate_subject = bundle.subject_dn
        client.certificate_issuer = bundle.issuer_dn
        client.certificate_valid_from = bundle.not_before
        client.certificate_valid_until = bundle.not_after
        client.vault_pki_serial = bundle.vault_pki_serial
        client.certificate_revoked_at = None
        client.certificate_revoked_by = None
        client.certificate_revocation_reason = None
        client.updated_at = datetime.now(timezone.utc)
        client.updated_by = current_user.email or current_user.id

        await db.flush()
        await db.refresh(client)

        logger.info(f"Renewed certificate for client {client.id}")

        # Publish event
        await event_bus.publish(EVENT_CERTIFICATE_RENEWED, {
            "client_id": str(client.id),
            "tenant_id": client.tenant_id,
            "previous_fingerprint": previous_fingerprint,
            "new_fingerprint": bundle.fingerprint_sha256,
            "new_serial": bundle.serial_number,
            "expires_at": bundle.not_after.isoformat(),
        })

        return CertificateRenewResponse(
            client=ClientResponse.from_model(client),
            certificate_bundle=CertificateBundleResponse(
                certificate_pem=bundle.certificate_pem,
                private_key_pem=bundle.private_key_pem,
                ca_chain_pem=bundle.ca_chain_pem,
                fingerprint_sha256=bundle.fingerprint_sha256,
                serial_number=bundle.serial_number,
                expires_at=bundle.not_after,
            ),
            previous_fingerprint=previous_fingerprint or "",
        )

    except CertificateServiceUnavailable as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )


@router.post("/{client_id}/certificate/revoke", response_model=ClientResponse)
async def revoke_client_certificate(
    client_id: UUID,
    body: CertificateRevokeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke client certificate."""

    _check_permission(current_user, Permission.CLIENTS_UPDATE)

    result = await db.execute(
        select(Client).where(
            and_(
                Client.id == client_id,
                Client.deleted_at.is_(None)
            )
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not _has_tenant_access(current_user, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not client.certificate_serial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client does not have a certificate"
        )

    if client.certificate_revoked_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certificate is already revoked"
        )

    # Revoke certificate
    cert_service = get_certificate_service()
    await cert_service.revoke_certificate(client.certificate_serial, body.reason)

    # Update client
    client.certificate_revoked_at = datetime.now(timezone.utc)
    client.certificate_revoked_by = current_user.email or current_user.id
    client.certificate_revocation_reason = body.reason
    client.status = ClientStatus.REVOKED
    client.updated_at = datetime.now(timezone.utc)
    client.updated_by = current_user.email or current_user.id

    await db.flush()
    await db.refresh(client)

    logger.info(f"Revoked certificate for client {client.id}: {body.reason}")

    # Publish event
    await event_bus.publish(EVENT_CERTIFICATE_REVOKED, {
        "client_id": str(client.id),
        "tenant_id": client.tenant_id,
        "fingerprint_sha256": client.certificate_fingerprint_sha256,
        "serial_number": client.certificate_serial,
        "reason": body.reason,
        "revoked_by": current_user.email or current_user.id,
    })

    return ClientResponse.from_model(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete a client."""

    _check_permission(current_user, Permission.CLIENTS_DELETE)

    result = await db.execute(
        select(Client).where(
            and_(
                Client.id == client_id,
                Client.deleted_at.is_(None)
            )
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not _has_tenant_access(current_user, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Revoke certificate if exists
    if client.certificate_serial and not client.certificate_revoked_at:
        cert_service = get_certificate_service()
        await cert_service.revoke_certificate(
            client.certificate_serial,
            reason="Client deleted"
        )
        client.certificate_revoked_at = datetime.now(timezone.utc)
        client.certificate_revoked_by = current_user.email or current_user.id
        client.certificate_revocation_reason = "Client deleted"

    # Soft delete
    client.deleted_at = datetime.now(timezone.utc)
    client.deleted_by = current_user.email or current_user.id
    client.status = ClientStatus.REVOKED

    await db.flush()

    logger.info(f"Deleted client {client.id}")

    # Publish event
    await event_bus.publish(EVENT_CLIENT_DELETED, {
        "client_id": str(client.id),
        "tenant_id": client.tenant_id,
        "deleted_by": current_user.email or current_user.id,
    })
