"""Self-service signup validation and orchestration (CAB-1541).

Extracts business logic from the self-service router:
- Email domain validation (disposable domain blocklist)
- Invite code validation (config-based)
- Plan selection (trial/standard)
- Tenant slug generation
- Idempotent tenant creation
"""

import asyncio
import logging
import re
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.tenant import Tenant, TenantProvisioningStatus, TenantStatus
from ..repositories.tenant import TenantRepository
from ..schemas.self_service import SelfServiceSignupRequest, SelfServiceSignupResponse, SignupPlan
from ..services.tenant_provisioning_service import provision_tenant

logger = logging.getLogger(__name__)

# Top disposable email domains — blocks throwaway signups.
# Override via SIGNUP_BLOCKED_EMAIL_DOMAINS env var (comma-separated).
_DEFAULT_BLOCKED_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "tempmail.com",
        "throwaway.email",
        "yopmail.com",
        "sharklasers.com",
        "grr.la",
        "guerrillamail.info",
        "guerrillamail.de",
        "temp-mail.org",
        "fakeinbox.com",
        "dispostable.com",
        "mailnesia.com",
        "maildrop.cc",
        "trashmail.com",
        "trashmail.me",
        "trashmail.net",
        "10minutemail.com",
        "tempail.com",
        "mohmal.com",
        "getnada.com",
        "emailondeck.com",
        "getairmail.com",
        "mailcatch.com",
    }
)

_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _get_blocked_domains() -> frozenset[str]:
    """Return the blocked domains set (config override or defaults)."""
    override = settings.SIGNUP_BLOCKED_EMAIL_DOMAINS
    if override:
        return frozenset(d.strip().lower() for d in override.split(",") if d.strip())
    return _DEFAULT_BLOCKED_DOMAINS


def validate_email_domain(email: str) -> None:
    """Raise HTTPException(400) if email uses a disposable domain."""
    domain = email.rsplit("@", 1)[-1].lower()
    blocked = _get_blocked_domains()
    if domain in blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Email domain '{domain}' is not allowed. Please use a work or personal email.",
        )


def validate_invite_code(code: str | None, plan: SignupPlan) -> None:
    """Validate invite code if required.

    - Standard plan always requires a valid invite code.
    - Trial plan: invite code optional (accepted but not required).
    """
    if plan == SignupPlan.STANDARD:
        if not code:
            raise HTTPException(status_code=400, detail="Invite code required for standard plan signup.")
        valid_codes = settings.signup_invite_codes_list
        if code not in valid_codes:
            raise HTTPException(status_code=400, detail="Invalid invite code.")
    elif code:
        # Trial plan with optional code — validate if provided
        valid_codes = settings.signup_invite_codes_list
        if valid_codes and code not in valid_codes:
            raise HTTPException(status_code=400, detail="Invalid invite code.")


def slugify_tenant_name(name: str) -> str:
    """Convert tenant name to a URL-safe slug ID."""
    slug = name.lower().replace(" ", "-")
    # Remove any characters not matching [a-z0-9-]
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    if not slug or not _TENANT_ID_RE.match(slug):
        raise HTTPException(status_code=400, detail="Tenant name produces an invalid ID.")
    return slug


async def signup_tenant(
    db: AsyncSession,
    signup_data: SelfServiceSignupRequest,
) -> SelfServiceSignupResponse:
    """Validate input, create tenant, fire provisioning.

    Returns SelfServiceSignupResponse. Idempotent: existing tenant returns current status.
    """
    # Step 1: Validate email domain
    validate_email_domain(signup_data.owner_email)

    # Step 2: Validate invite code
    validate_invite_code(signup_data.invite_code, signup_data.plan)

    # Step 3: Generate tenant ID
    tenant_id = slugify_tenant_name(signup_data.name)

    repo = TenantRepository(db)

    # Step 4: Idempotency — check existing
    existing = await repo.get_by_id(tenant_id)
    if existing:
        existing_plan = (existing.settings or {}).get("plan", "trial")
        if existing.provisioning_status == TenantProvisioningStatus.READY.value:
            return SelfServiceSignupResponse(
                tenant_id=existing.id,
                status="ready",
                plan=existing_plan,
                poll_url=f"/v1/self-service/tenants/{existing.id}/status",
            )
        return SelfServiceSignupResponse(
            tenant_id=existing.id,
            status=existing.provisioning_status or "pending",
            plan=existing_plan,
            poll_url=f"/v1/self-service/tenants/{existing.id}/status",
        )

    # Step 5: Create new tenant
    tenant = Tenant(
        id=tenant_id,
        name=signup_data.display_name,
        description=signup_data.company or "",
        status=TenantStatus.ACTIVE.value,
        provisioning_status=TenantProvisioningStatus.PENDING.value,
        settings={
            "owner_email": signup_data.owner_email,
            "plan": signup_data.plan.value,
        },
    )
    await repo.create(tenant)
    await db.commit()

    # Step 6: Fire async provisioning
    correlation_id = str(uuid.uuid4())
    asyncio.create_task(
        provision_tenant(
            tenant_id=tenant_id,
            owner_email=signup_data.owner_email,
            display_name=signup_data.display_name,
            correlation_id=correlation_id,
        )
    )

    logger.info("Self-service signup: tenant=%s plan=%s", tenant_id, signup_data.plan.value)

    return SelfServiceSignupResponse(
        tenant_id=tenant_id,
        status="provisioning",
        plan=signup_data.plan.value,
        poll_url=f"/v1/self-service/tenants/{tenant_id}/status",
    )
