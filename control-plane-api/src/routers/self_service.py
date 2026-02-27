"""Self-service tenant signup router (CAB-1315, CAB-1541).

Public endpoints (no auth) with rate limiting for DDoS mitigation.
Response MUST NOT include owner_email (PII leak risk on public endpoint).
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models.tenant import TenantProvisioningStatus
from ..repositories.tenant import TenantRepository
from ..schemas.self_service import (
    SelfServiceSignupRequest,
    SelfServiceSignupResponse,
    SelfServiceStatusResponse,
)
from ..services.signup_service import signup_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/self-service", tags=["Self-Service"])


@router.post("/tenants", response_model=SelfServiceSignupResponse, status_code=202)
@limiter.limit("5/minute")
async def self_service_signup(
    request: Request,
    signup_data: SelfServiceSignupRequest,
):
    """Self-service tenant signup (public, rate-limited 5 req/min per IP)."""
    async for db in get_db():
        try:
            return await signup_tenant(db, signup_data)
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

            plan = (tenant.settings or {}).get("plan")

            return SelfServiceStatusResponse(
                tenant_id=tenant.id,
                provisioning_status=tenant.provisioning_status or "pending",
                plan=plan,
                ready_at=ready_at,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Self-service status check failed for {tenant_id}: {e}")
            raise HTTPException(status_code=500, detail="Status check failed")
        break

    raise HTTPException(status_code=500, detail="Database unavailable")
