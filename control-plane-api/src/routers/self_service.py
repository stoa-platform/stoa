"""Self-service tenant signup router (CAB-1315).

Public endpoints (no auth) with rate limiting for DDoS mitigation.
Response MUST NOT include owner_email (PII leak risk on public endpoint).
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request

from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models.tenant import Tenant, TenantProvisioningStatus, TenantStatus
from ..repositories.tenant import TenantRepository
from ..schemas.self_service import (
    SelfServiceSignupRequest,
    SelfServiceSignupResponse,
    SelfServiceStatusResponse,
)
from ..services.tenant_provisioning_service import provision_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/self-service", tags=["Self-Service"])


@router.post("/tenants", response_model=SelfServiceSignupResponse, status_code=202)
@limiter.limit("5/minute")
async def self_service_signup(
    request: Request,
    signup_data: SelfServiceSignupRequest,
):
    """Self-service tenant signup (public, rate-limited 5 req/min per IP)."""
    tenant_id = signup_data.name.lower().replace(" ", "-")

    async for db in get_db():
        try:
            repo = TenantRepository(db)

            # Idempotency: if tenant already exists
            existing = await repo.get_by_id(tenant_id)
            if existing:
                if existing.provisioning_status == TenantProvisioningStatus.READY.value:
                    # Already provisioned — return 200 (not 202)
                    return SelfServiceSignupResponse(
                        tenant_id=existing.id,
                        status="ready",
                        poll_url=f"/v1/self-service/tenants/{existing.id}/status",
                    )
                # Still provisioning
                return SelfServiceSignupResponse(
                    tenant_id=existing.id,
                    status=existing.provisioning_status or "pending",
                    poll_url=f"/v1/self-service/tenants/{existing.id}/status",
                )

            # Create new tenant
            tenant = Tenant(
                id=tenant_id,
                name=signup_data.display_name,
                description=signup_data.company or "",
                status=TenantStatus.ACTIVE.value,
                provisioning_status=TenantProvisioningStatus.PENDING.value,
                settings={"owner_email": signup_data.owner_email},
            )

            await repo.create(tenant)
            await db.commit()

            # Fire async provisioning
            correlation_id = str(uuid.uuid4())
            asyncio.create_task(
                provision_tenant(
                    tenant_id=tenant_id,
                    owner_email=signup_data.owner_email,
                    display_name=signup_data.display_name,
                    correlation_id=correlation_id,
                )
            )

            logger.info(f"Self-service signup for tenant {tenant_id}")

            return SelfServiceSignupResponse(
                tenant_id=tenant_id,
                status="provisioning",
                poll_url=f"/v1/self-service/tenants/{tenant_id}/status",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Self-service signup failed: {e}")
            raise HTTPException(status_code=500, detail="Signup failed")
        break  # Only iterate once through the generator

    raise HTTPException(status_code=500, detail="Database unavailable")


@router.get("/tenants/{tenant_id}/status", response_model=SelfServiceStatusResponse)
@limiter.limit("30/minute")
async def self_service_status(
    request: Request,
    tenant_id: str,
):
    """Poll tenant provisioning status (public, rate-limited)."""
    async for db in get_db():
        try:
            repo = TenantRepository(db)
            tenant = await repo.get_by_id(tenant_id)

            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            ready_at = None
            if tenant.provisioning_status == TenantProvisioningStatus.READY.value and tenant.updated_at:
                ready_at = tenant.updated_at.isoformat()

            return SelfServiceStatusResponse(
                tenant_id=tenant.id,
                provisioning_status=tenant.provisioning_status or "pending",
                ready_at=ready_at,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Self-service status check failed for {tenant_id}: {e}")
            raise HTTPException(status_code=500, detail="Status check failed")
        break

    raise HTTPException(status_code=500, detail="Database unavailable")
