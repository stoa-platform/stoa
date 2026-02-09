"""Consumers router - External API consumer management (CAB-1121 + CAB-864)."""

import csv
import io
import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..config import settings
from ..database import get_db
from ..models.consumer import CertificateStatus, Consumer, ConsumerStatus
from ..models.plan import Plan
from ..models.subscription import Subscription
from ..repositories.consumer import ConsumerRepository
from ..repositories.quota_usage import QuotaUsageRepository
from ..schemas.consumer import (
    BulkResultItem,
    BulkResultResponse,
    CertificateRotateRequest,
    ConsumerCreate,
    ConsumerCredentialsResponse,
    ConsumerListResponse,
    ConsumerResponse,
    ConsumerStatusEnum,
    ConsumerUpdate,
)
from ..schemas.quota import QuotaCounters, QuotaLimits, QuotaRemaining, QuotaResets, QuotaStatusResponse
from ..services.certificate_utils import parse_pem_certificate, validate_certificate_not_expired
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/consumers", tags=["Consumers"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


# ============== CRUD Endpoints ==============


@router.post("/{tenant_id}", response_model=ConsumerResponse, status_code=201)
async def create_consumer(
    tenant_id: str,
    request: ConsumerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new consumer for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)

    # Check for duplicate external_id
    existing = await repo.get_by_external_id(tenant_id, request.external_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Consumer with external_id '{request.external_id}' already exists in this tenant",
        )

    consumer = Consumer(
        external_id=request.external_id,
        name=request.name,
        email=request.email,
        company=request.company,
        description=request.description,
        tenant_id=tenant_id,
        keycloak_user_id=request.keycloak_user_id,
        status=ConsumerStatus.ACTIVE,
        consumer_metadata=request.consumer_metadata,
        created_by=user.id,
    )

    try:
        consumer = await repo.create(consumer)
        logger.info(
            f"Created consumer {consumer.id} external_id={request.external_id} " f"tenant={tenant_id} by={user.email}"
        )
    except Exception as e:
        logger.error(f"Failed to create consumer: {e}")
        raise HTTPException(status_code=500, detail="Failed to create consumer")

    # Consumer is active by default — create Keycloak OAuth2 client
    try:
        kc_result = await keycloak_service.create_consumer_client(
            tenant_slug=tenant_id,
            consumer_external_id=request.external_id,
            consumer_id=str(consumer.id),
        )
        consumer.keycloak_client_id = kc_result["client_id"]
        consumer = await repo.update(consumer)
    except RuntimeError as e:
        logger.error(f"Keycloak unavailable during consumer creation: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication service unavailable, retry later"},
            headers={"Retry-After": "5"},
        )
    except Exception as e:
        logger.warning(f"Failed to create Keycloak client for consumer {consumer.id}: {e}")

    return ConsumerResponse.model_validate(consumer)


@router.get("/{tenant_id}", response_model=ConsumerListResponse)
async def list_consumers(
    tenant_id: str,
    status: ConsumerStatusEnum | None = None,
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List consumers for a tenant with optional filtering."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)

    db_status = ConsumerStatus(status.value) if status else None
    consumers, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        search=search,
        page=page,
        page_size=page_size,
    )

    return ConsumerListResponse(
        items=[ConsumerResponse.model_validate(c) for c in consumers],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{tenant_id}/{consumer_id}", response_model=ConsumerResponse)
async def get_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get consumer details by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    return ConsumerResponse.model_validate(consumer)


@router.put("/{tenant_id}/{consumer_id}", response_model=ConsumerResponse)
async def update_consumer(
    tenant_id: str,
    consumer_id: UUID,
    request: ConsumerUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update consumer details."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    # Apply updates
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(consumer, field, value)

    consumer = await repo.update(consumer)

    logger.info(f"Updated consumer {consumer_id} by {user.email}")

    return ConsumerResponse.model_validate(consumer)


@router.delete("/{tenant_id}/{consumer_id}", status_code=204)
async def delete_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    await repo.delete(consumer)

    logger.info(f"Deleted consumer {consumer_id} by {user.email}")


# ============== Status Management Endpoints ==============


@router.post("/{tenant_id}/{consumer_id}/suspend", response_model=ConsumerResponse)
async def suspend_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suspend an active consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status != ConsumerStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot suspend consumer in {consumer.status.value} status",
        )

    consumer = await repo.update_status(consumer, ConsumerStatus.SUSPENDED)
    logger.info(f"Consumer {consumer_id} suspended by {user.email}")

    return ConsumerResponse.model_validate(consumer)


@router.post("/{tenant_id}/{consumer_id}/activate", response_model=ConsumerResponse)
async def activate_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a suspended consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status != ConsumerStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate consumer in {consumer.status.value} status",
        )

    consumer = await repo.update_status(consumer, ConsumerStatus.ACTIVE)
    logger.info(f"Consumer {consumer_id} activated by {user.email}")

    # Create Keycloak client if not already present
    if not consumer.keycloak_client_id:
        try:
            kc_result = await keycloak_service.create_consumer_client(
                tenant_slug=tenant_id,
                consumer_external_id=consumer.external_id,
                consumer_id=str(consumer.id),
            )
            consumer.keycloak_client_id = kc_result["client_id"]
            consumer = await repo.update(consumer)
        except RuntimeError as e:
            logger.error(f"Keycloak unavailable during consumer activation: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication service unavailable, retry later"},
                headers={"Retry-After": "5"},
            )
        except Exception as e:
            logger.warning(f"Failed to create Keycloak client for consumer {consumer_id}: {e}")

    return ConsumerResponse.model_validate(consumer)


@router.post("/{tenant_id}/{consumer_id}/block", response_model=ConsumerResponse)
async def block_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a consumer (permanent until unblocked)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status == ConsumerStatus.BLOCKED:
        raise HTTPException(status_code=400, detail="Consumer is already blocked")

    consumer = await repo.update_status(consumer, ConsumerStatus.BLOCKED)
    logger.info(f"Consumer {consumer_id} blocked by {user.email}")

    return ConsumerResponse.model_validate(consumer)


# ============== Credentials Endpoint ==============


@router.get("/{tenant_id}/{consumer_id}/credentials", response_model=ConsumerCredentialsResponse)
async def get_consumer_credentials(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get consumer OAuth2 credentials (one-time secret display).

    Regenerates the client secret each time it is called so the secret
    is only visible once per request.  The caller must store it securely.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status != ConsumerStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Consumer must be active to retrieve credentials")

    if not consumer.keycloak_client_id:
        raise HTTPException(status_code=404, detail="No Keycloak client configured for this consumer")

    try:
        client = await keycloak_service.get_client(consumer.keycloak_client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Keycloak client not found")

        client_uuid = client["id"]
        secret_data = keycloak_service._admin.generate_client_secrets(client_uuid)

        token_endpoint = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"

        logger.info(f"Credentials retrieved for consumer {consumer_id} by {user.email}")

        return ConsumerCredentialsResponse(
            consumer_id=consumer.id,
            client_id=consumer.keycloak_client_id,
            client_secret=secret_data.get("value", ""),
            token_endpoint=token_endpoint,
        )
    except RuntimeError as e:
        logger.error(f"Keycloak unavailable for credentials retrieval: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication service unavailable, retry later"},
            headers={"Retry-After": "5"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve credentials for consumer {consumer_id}: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication service unavailable, retry later"},
            headers={"Retry-After": "5"},
        )


# ============== Bulk Onboarding (CAB-864 Phase 3) ==============

MAX_BULK_ROWS = 100
REQUIRED_CSV_FIELDS = {"external_id", "name", "email"}


@router.post("/{tenant_id}/bulk", response_model=BulkResultResponse)
async def bulk_create_consumers(
    tenant_id: str,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk onboard consumers from a CSV file (CAB-864).

    CSV columns: external_id, name, email, company (optional), certificate_pem (optional).
    Max 100 rows per request. Each row is processed independently.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    # Read and validate CSV
    try:
        content = await file.read()
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV file")

    missing_fields = REQUIRED_CSV_FIELDS - set(reader.fieldnames)
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required CSV columns: {', '.join(sorted(missing_fields))}",
        )

    rows = list(reader)
    if len(rows) > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BULK_ROWS} rows per request, got {len(rows)}",
        )

    if not rows:
        raise HTTPException(status_code=400, detail="CSV file contains no data rows")

    repo = ConsumerRepository(db)
    results: list[BulkResultItem] = []
    success_count = 0
    failed_count = 0

    for row_num, row in enumerate(rows, start=1):
        result = await _process_bulk_row(
            row_num=row_num, row=row, tenant_id=tenant_id, user=user, repo=repo, db=db,
        )
        results.append(result)
        if result.status == "created":
            success_count += 1
        else:
            failed_count += 1

    await db.commit()

    logger.info(
        f"Bulk onboarding for tenant {tenant_id}: {success_count}/{len(rows)} created, "
        f"{failed_count} failed, by {user.email}"
    )

    return BulkResultResponse(
        total=len(rows), success=success_count, failed=failed_count, results=results,
    )


async def _process_bulk_row(
    row_num: int, row: dict, tenant_id: str, user: User,
    repo: ConsumerRepository, db: AsyncSession,
) -> BulkResultItem:
    """Process a single row from bulk CSV upload."""
    external_id = row.get("external_id", "").strip()
    name = row.get("name", "").strip()
    email = row.get("email", "").strip()
    company = row.get("company", "").strip() or None
    certificate_pem = row.get("certificate_pem", "").strip() or None

    if not external_id:
        return BulkResultItem(row=row_num, status="error", error="Missing required field: external_id")
    if not name:
        return BulkResultItem(
            row=row_num, status="error", external_id=external_id, error="Missing required field: name"
        )
    if not email:
        return BulkResultItem(
            row=row_num, status="error", external_id=external_id, error="Missing required field: email"
        )

    existing = await repo.get_by_external_id(tenant_id, external_id)
    if existing:
        return BulkResultItem(
            row=row_num, status="error", external_id=external_id,
            error="Consumer with external_id already exists",
        )

    cert_info = None
    if certificate_pem:
        try:
            cert_info = parse_pem_certificate(certificate_pem)
            validate_certificate_not_expired(cert_info)
        except ValueError as e:
            return BulkResultItem(
                row=row_num, status="error", external_id=external_id, error=str(e)
            )

        dup = await repo.get_by_fingerprint(tenant_id, cert_info.fingerprint_hex)
        if dup:
            return BulkResultItem(
                row=row_num, status="error", external_id=external_id,
                error="Certificate fingerprint already registered",
            )

    consumer = Consumer(
        external_id=external_id, name=name, email=email, company=company,
        tenant_id=tenant_id, status=ConsumerStatus.ACTIVE, created_by=user.id,
    )

    if cert_info:
        consumer.certificate_fingerprint = cert_info.fingerprint_hex
        consumer.certificate_subject_dn = cert_info.subject_dn
        consumer.certificate_issuer_dn = cert_info.issuer_dn
        consumer.certificate_serial = cert_info.serial
        consumer.certificate_not_before = cert_info.not_before
        consumer.certificate_not_after = cert_info.not_after
        consumer.certificate_pem = cert_info.pem
        consumer.certificate_status = CertificateStatus.ACTIVE

    try:
        consumer = await repo.create(consumer)
    except Exception as e:
        logger.error(f"Bulk row {row_num}: failed to create consumer: {e}")
        return BulkResultItem(
            row=row_num, status="error", external_id=external_id, error="Database error"
        )

    client_id = None
    client_secret = None
    try:
        if cert_info:
            kc_result = await keycloak_service.create_consumer_client_with_cert(
                tenant_slug=tenant_id, consumer_external_id=external_id,
                consumer_id=str(consumer.id), fingerprint_b64url=cert_info.fingerprint_b64url,
            )
        else:
            kc_result = await keycloak_service.create_consumer_client(
                tenant_slug=tenant_id, consumer_external_id=external_id,
                consumer_id=str(consumer.id),
            )
        client_id = kc_result["client_id"]
        client_secret = kc_result["client_secret"]
        consumer.keycloak_client_id = client_id
        await repo.update(consumer)
    except Exception as e:
        logger.warning(f"Bulk row {row_num}: Keycloak client creation failed: {e}")

    return BulkResultItem(
        row=row_num, status="created", external_id=external_id,
        consumer_id=consumer.id, client_id=client_id, client_secret=client_secret,
    )


# ============== Certificate Revocation (CAB-864) ==============


@router.post("/{tenant_id}/{consumer_id}/certificate/revoke", response_model=ConsumerResponse)
async def revoke_certificate(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a consumer's mTLS certificate (CAB-864).

    Sets certificate_status to 'revoked' and disables the Keycloak client.
    Idempotent — revoking an already-revoked certificate is a no-op.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")
    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")
    if not consumer.certificate_fingerprint:
        raise HTTPException(status_code=400, detail="Consumer has no certificate to revoke")

    if consumer.certificate_status == CertificateStatus.REVOKED:
        return ConsumerResponse.model_validate(consumer)

    consumer.certificate_status = CertificateStatus.REVOKED
    consumer.certificate_fingerprint_previous = None
    consumer.previous_cert_expires_at = None
    consumer = await repo.update(consumer)

    if consumer.keycloak_client_id:
        try:
            await keycloak_service.disable_consumer_client(consumer.keycloak_client_id)
        except Exception as e:
            logger.warning(f"Failed to disable Keycloak client for consumer {consumer_id}: {e}")

    await db.commit()
    logger.info(f"Certificate revoked for consumer {consumer_id} by {user.email}")

    return ConsumerResponse.model_validate(consumer)


# ============== Certificate Rotation (CAB-864) ==============


@router.post("/{tenant_id}/{consumer_id}/certificate/rotate", response_model=ConsumerResponse)
async def rotate_certificate(
    tenant_id: str,
    consumer_id: UUID,
    request: CertificateRotateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate a consumer's mTLS certificate (CAB-864).

    Accepts a new PEM certificate, moves the current fingerprint to
    certificate_fingerprint_previous, and sets a grace period.
    """
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")
    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")
    if not consumer.certificate_fingerprint:
        raise HTTPException(status_code=400, detail="Consumer has no certificate to rotate")
    if consumer.certificate_status == CertificateStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Cannot rotate a revoked certificate")

    try:
        cert_info = parse_pem_certificate(request.certificate_pem)
        validate_certificate_not_expired(cert_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    dup = await repo.get_by_fingerprint(tenant_id, cert_info.fingerprint_hex)
    if dup and dup.id != consumer.id:
        raise HTTPException(status_code=409, detail="Certificate fingerprint already registered")

    consumer.certificate_fingerprint_previous = consumer.certificate_fingerprint
    consumer.certificate_fingerprint = cert_info.fingerprint_hex
    consumer.certificate_subject_dn = cert_info.subject_dn
    consumer.certificate_issuer_dn = cert_info.issuer_dn
    consumer.certificate_serial = cert_info.serial
    consumer.certificate_not_before = cert_info.not_before
    consumer.certificate_not_after = cert_info.not_after
    consumer.certificate_pem = cert_info.pem
    consumer.certificate_status = CertificateStatus.ROTATING
    consumer.previous_cert_expires_at = datetime.now(UTC) + timedelta(
        hours=request.grace_period_hours
    )
    consumer.last_rotated_at = datetime.now(UTC)
    consumer.rotation_count = (consumer.rotation_count or 0) + 1

    consumer = await repo.update(consumer)

    if consumer.keycloak_client_id:
        try:
            await keycloak_service.update_consumer_client_cnf(
                consumer.keycloak_client_id, cert_info.fingerprint_b64url,
            )
        except Exception as e:
            logger.warning(f"Failed to update Keycloak cnf for consumer {consumer_id}: {e}")

    await db.commit()
    logger.info(
        f"Certificate rotated for consumer {consumer_id} by {user.email}, "
        f"grace period {request.grace_period_hours}h"
    )

    return ConsumerResponse.model_validate(consumer)


# ============== Quota Status (CAB-1121 Phase 4) ==============


@router.get("/{tenant_id}/{consumer_id}/quota", response_model=QuotaStatusResponse)
async def get_consumer_quota_status(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a consumer's current quota status (usage + remaining + resets)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)
    if not consumer or consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    # Look up plan limits via subscription
    from sqlalchemy import select as sa_select

    sub_result = await db.execute(
        sa_select(Subscription.plan_id).where(
            Subscription.consumer_id == consumer_id,
            Subscription.tenant_id == tenant_id,
            Subscription.status == "active",
        ).limit(1)
    )
    sub_row = sub_result.first()

    daily_limit = None
    monthly_limit = None
    if sub_row and sub_row.plan_id:
        plan_result = await db.execute(sa_select(Plan).where(Plan.id == sub_row.plan_id))
        plan = plan_result.scalar_one_or_none()
        if plan:
            daily_limit = plan.daily_request_limit
            monthly_limit = plan.monthly_request_limit

    # Get current usage
    quota_repo = QuotaUsageRepository(db)
    usage = await quota_repo.get_current(consumer_id, tenant_id)

    daily_used = usage.request_count_daily if usage else 0
    monthly_used = usage.request_count_monthly if usage else 0

    # Compute remaining
    daily_remaining = (daily_limit - daily_used) if daily_limit is not None else None
    monthly_remaining = (monthly_limit - monthly_used) if monthly_limit is not None else None

    # Compute reset timestamps
    now = datetime.utcnow()
    daily_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        monthly_reset = now.replace(
            year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        monthly_reset = now.replace(
            month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    return QuotaStatusResponse(
        consumer_id=consumer_id,
        tenant_id=tenant_id,
        plan=QuotaLimits(
            daily_request_limit=daily_limit,
            monthly_request_limit=monthly_limit,
        ),
        usage=QuotaCounters(daily=daily_used, monthly=monthly_used),
        remaining=QuotaRemaining(daily=daily_remaining, monthly=monthly_remaining),
        resets_at=QuotaResets(daily=daily_reset, monthly=monthly_reset),
    )
