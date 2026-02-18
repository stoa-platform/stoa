"""Onboarding endpoints for zero-touch developer trial (CAB-1325)."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.models.saas_api_key import SaasApiKey, SaasApiKeyStatus
from src.repositories.backend_api import SaasApiKeyRepository
from src.repositories.onboarding import OnboardingRepository
from src.schemas.onboarding import (
    OnboardingCompleteResponse,
    OnboardingProgressResponse,
    OnboardingStepUpdate,
    TrialKeyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/me/onboarding", tags=["Onboarding"])

VALID_STEPS = ["choose_use_case", "create_app", "subscribe_api", "first_call"]

TRIAL_KEY_NAME = "trial-key"
TRIAL_KEY_RPM = 100
TRIAL_KEY_DAYS = 30


@router.get("", response_model=OnboardingProgressResponse)
async def get_onboarding_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current onboarding progress. Auto-creates if none exists."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant provisioned yet")

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    await db.commit()

    return OnboardingProgressResponse(
        tenant_id=progress.tenant_id,
        user_id=progress.user_id,
        steps_completed=progress.steps_completed or {},
        started_at=progress.started_at,
        completed_at=progress.completed_at,
        ttftc_seconds=progress.ttftc_seconds,
        is_complete=progress.completed_at is not None,
    )


@router.put("/steps/{step_name}", response_model=OnboardingProgressResponse)
async def mark_step_complete(
    step_name: str,
    _body: OnboardingStepUpdate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an onboarding step as completed. Idempotent."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant provisioned yet")

    if step_name not in VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step: {step_name}. Valid: {VALID_STEPS}",
        )

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    progress = await repo.upsert_step(progress, step_name)
    await db.commit()

    return OnboardingProgressResponse(
        tenant_id=progress.tenant_id,
        user_id=progress.user_id,
        steps_completed=progress.steps_completed or {},
        started_at=progress.started_at,
        completed_at=progress.completed_at,
        ttftc_seconds=progress.ttftc_seconds,
        is_complete=progress.completed_at is not None,
    )


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding as fully completed."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant provisioned yet")

    repo = OnboardingRepository(db)
    progress = await repo.get_or_create(current_user.tenant_id, current_user.id)
    progress = await repo.mark_complete(progress)
    await db.commit()

    return OnboardingCompleteResponse(
        completed=True,
        ttftc_seconds=progress.ttftc_seconds,
    )


# ============== Phase 2: Trial Key Endpoints ==============


def _generate_trial_key() -> tuple[str, str, str]:
    """Generate a trial API key. Returns (plaintext, key_hash, key_prefix)."""
    random_part = secrets.token_hex(32)
    prefix_hex = secrets.token_hex(2)
    prefix = f"stoa_trial_{prefix_hex}"
    plaintext = f"{prefix}_{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash, prefix


@router.get("/trial-key", response_model=TrialKeyResponse)
async def get_trial_key_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trial API key metadata (NOT plaintext). Returns 404 if no trial key exists."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant provisioned yet")

    key_repo = SaasApiKeyRepository(db)
    keys, _ = await key_repo.list_by_tenant(current_user.tenant_id, page=1, page_size=100)
    trial_key = next((k for k in keys if k.name == TRIAL_KEY_NAME), None)

    if not trial_key:
        raise HTTPException(status_code=404, detail="No trial key found")

    return TrialKeyResponse(
        key_prefix=trial_key.key_prefix,
        name=trial_key.name,
        rate_limit_rpm=trial_key.rate_limit_rpm or TRIAL_KEY_RPM,
        expires_at=trial_key.expires_at,
        status=trial_key.status.value if hasattr(trial_key.status, "value") else str(trial_key.status),
        created_at=trial_key.created_at,
    )


@router.post("/regenerate-trial-key", response_model=TrialKeyResponse, status_code=201)
async def regenerate_trial_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate trial API key (revokes old one, creates new). Returns metadata only."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant provisioned yet")

    key_repo = SaasApiKeyRepository(db)

    # Revoke existing trial key if any
    keys, _ = await key_repo.list_by_tenant(current_user.tenant_id, page=1, page_size=100)
    for key in keys:
        if key.name == TRIAL_KEY_NAME and key.status == SaasApiKeyStatus.ACTIVE:
            key.status = SaasApiKeyStatus.REVOKED
            key.revoked_at = datetime.now(UTC)
            await key_repo.update(key)

    # Generate new trial key
    _plaintext, key_hash, prefix = _generate_trial_key()
    now = datetime.now(UTC)

    new_key = SaasApiKey(
        tenant_id=current_user.tenant_id,
        name=TRIAL_KEY_NAME,
        description="Auto-generated trial key (regenerated)",
        key_hash=key_hash,
        key_prefix=prefix,
        allowed_backend_api_ids=[],
        rate_limit_rpm=TRIAL_KEY_RPM,
        expires_at=now + timedelta(days=TRIAL_KEY_DAYS),
        created_by=current_user.id,
    )
    new_key = await key_repo.create(new_key)
    await db.commit()

    logger.info("Trial key regenerated for tenant %s by %s", current_user.tenant_id, current_user.id)

    return TrialKeyResponse(
        key_prefix=new_key.key_prefix,
        name=new_key.name,
        rate_limit_rpm=new_key.rate_limit_rpm or TRIAL_KEY_RPM,
        expires_at=new_key.expires_at,
        status="active",
        created_at=new_key.created_at,
    )
