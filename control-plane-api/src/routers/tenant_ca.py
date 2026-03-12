"""Tenant CA router — per-tenant CA keypair management and CSR signing (CAB-1787).

Endpoints:
  POST /v1/tenants/{tenant_id}/ca/generate  — Generate CA keypair
  GET  /v1/tenants/{tenant_id}/ca           — Get CA certificate (public only)
  POST /v1/tenants/{tenant_id}/ca/sign      — Sign a CSR
  DELETE /v1/tenants/{tenant_id}/ca         — Revoke CA (cpi-admin only)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..database import get_db
from ..models.tenant import Tenant
from ..models.tenant_ca import TenantCA
from ..services.tenant_ca_service import generate_ca_keypair, sign_csr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/ca", tags=["Tenant CA"])


# --- Schemas ---


class CAGenerateResponse(BaseModel):
    tenant_id: str
    subject_dn: str
    serial_number: str
    not_before: str
    not_after: str
    key_algorithm: str
    fingerprint_sha256: str
    ca_certificate_pem: str
    status: str


class CAInfoResponse(BaseModel):
    tenant_id: str
    subject_dn: str
    serial_number: str
    not_before: str
    not_after: str
    key_algorithm: str
    fingerprint_sha256: str
    ca_certificate_pem: str
    status: str
    created_at: str


class CSRSignRequest(BaseModel):
    csr_pem: str = Field(..., description="PEM-encoded Certificate Signing Request")
    validity_days: int = Field(default=365, ge=1, le=3650, description="Certificate validity in days")


class CSRSignResponse(BaseModel):
    signed_certificate_pem: str
    subject_dn: str
    issuer_dn: str
    validity_days: int


# --- Helpers ---


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to the given tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _require_admin_or_tenant_admin(user: User, tenant_id: str) -> None:
    """Require cpi-admin or tenant-admin role with tenant access."""
    if "cpi-admin" in user.roles:
        return
    if "tenant-admin" in user.roles and user.tenant_id == tenant_id:
        return
    raise HTTPException(status_code=403, detail="Requires cpi-admin or tenant-admin role")


# --- Endpoints ---


@router.post("/generate", response_model=CAGenerateResponse, status_code=201)
async def generate_tenant_ca(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CAGenerateResponse:
    """Generate a new CA keypair for a tenant.

    Requires cpi-admin or tenant-admin role.
    Only one active CA per tenant is allowed.
    """
    _require_admin_or_tenant_admin(user, tenant_id)

    # Verify tenant exists
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    # Check for existing active CA
    result = await db.execute(select(TenantCA).where(TenantCA.tenant_id == tenant_id, TenantCA.status == "active"))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Tenant already has an active CA. Revoke it first to generate a new one.",
        )

    # Generate CA keypair
    ca_data = generate_ca_keypair(tenant_id, tenant.name)

    # Store in database
    tenant_ca = TenantCA(
        tenant_id=tenant_id,
        ca_certificate_pem=ca_data["ca_certificate_pem"],
        encrypted_private_key=ca_data["encrypted_private_key"],
        subject_dn=ca_data["subject_dn"],
        serial_number=ca_data["serial_number"],
        not_before=ca_data["not_before"],
        not_after=ca_data["not_after"],
        key_algorithm=ca_data["key_algorithm"],
        fingerprint_sha256=ca_data["fingerprint_sha256"],
    )
    db.add(tenant_ca)
    await db.flush()

    logger.info("Generated CA for tenant %s by user %s", tenant_id, user.id)

    return CAGenerateResponse(
        tenant_id=tenant_id,
        subject_dn=ca_data["subject_dn"],
        serial_number=ca_data["serial_number"],
        not_before=ca_data["not_before"].isoformat(),
        not_after=ca_data["not_after"].isoformat(),
        key_algorithm=ca_data["key_algorithm"],
        fingerprint_sha256=ca_data["fingerprint_sha256"],
        ca_certificate_pem=ca_data["ca_certificate_pem"],
        status="active",
    )


@router.get("", response_model=CAInfoResponse)
async def get_tenant_ca(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CAInfoResponse:
    """Get the active CA certificate for a tenant.

    Returns the public CA certificate only. Private key is never exposed.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    result = await db.execute(select(TenantCA).where(TenantCA.tenant_id == tenant_id, TenantCA.status == "active"))
    ca = result.scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail=f"No active CA found for tenant '{tenant_id}'")

    return CAInfoResponse(
        tenant_id=ca.tenant_id,
        subject_dn=ca.subject_dn,
        serial_number=ca.serial_number,
        not_before=ca.not_before.isoformat(),
        not_after=ca.not_after.isoformat(),
        key_algorithm=ca.key_algorithm,
        fingerprint_sha256=ca.fingerprint_sha256,
        ca_certificate_pem=ca.ca_certificate_pem,
        status=ca.status,
        created_at=ca.created_at.isoformat() if ca.created_at else "",
    )


@router.post("/sign", response_model=CSRSignResponse)
async def sign_consumer_csr(
    tenant_id: str,
    request: CSRSignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CSRSignResponse:
    """Sign a CSR with the tenant's CA private key.

    Requires cpi-admin or tenant-admin role.
    The CSR must have a valid signature.
    """
    _require_admin_or_tenant_admin(user, tenant_id)

    # Load active CA
    result = await db.execute(select(TenantCA).where(TenantCA.tenant_id == tenant_id, TenantCA.status == "active"))
    ca = result.scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail=f"No active CA found for tenant '{tenant_id}'")

    try:
        signed_pem = sign_csr(
            csr_pem=request.csr_pem,
            ca_cert_pem=ca.ca_certificate_pem,
            encrypted_private_key=ca.encrypted_private_key,
            validity_days=request.validity_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Parse signed cert to extract subject/issuer for response
    from cryptography import x509 as x509_mod

    signed_cert = x509_mod.load_pem_x509_certificate(signed_pem.encode("utf-8"))

    logger.info("Signed CSR for tenant %s by user %s", tenant_id, user.id)

    return CSRSignResponse(
        signed_certificate_pem=signed_pem,
        subject_dn=signed_cert.subject.rfc4514_string(),
        issuer_dn=signed_cert.issuer.rfc4514_string(),
        validity_days=request.validity_days,
    )


@router.delete("", status_code=200)
async def revoke_tenant_ca(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke the active CA for a tenant.

    Requires cpi-admin role only. This is a destructive operation —
    all certificates signed by this CA will no longer be trusted.
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only cpi-admin can revoke a tenant CA")

    result = await db.execute(select(TenantCA).where(TenantCA.tenant_id == tenant_id, TenantCA.status == "active"))
    ca = result.scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail=f"No active CA found for tenant '{tenant_id}'")

    ca.status = "revoked"
    await db.flush()

    logger.info("Revoked CA for tenant %s by user %s", tenant_id, user.id)

    return {"detail": f"CA for tenant '{tenant_id}' has been revoked", "tenant_id": tenant_id}
