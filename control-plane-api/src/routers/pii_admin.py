"""PII Admin API — scan and detect PII in text (CAB-430).

Provides cpi-admin endpoints for compliance auditing:
- POST /v1/admin/pii/scan  — detect PII types in arbitrary text
- POST /v1/admin/pii/mask  — mask PII in arbitrary text
- GET  /v1/admin/pii/config — return current PII masking configuration
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import User, get_current_user
from ..core.pii import (
    PIIType,
    get_masker,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/pii",
    tags=["Admin - PII Masking"],
)


# ── Schemas ──────────────────────────────────────────────────────────────


class PIIScanRequest(BaseModel):
    text: str = Field(..., max_length=100_000, description="Text to scan for PII")


class PIIDetection(BaseModel):
    pii_type: str
    count: int


class PIIScanResponse(BaseModel):
    detections: list[PIIDetection]
    total_pii_count: int
    text_length: int


class PIIMaskRequest(BaseModel):
    text: str = Field(..., max_length=100_000, description="Text to mask")


class PIIMaskResponse(BaseModel):
    masked_text: str
    original_length: int
    masked_length: int
    detections: list[PIIDetection]


class PIIConfigResponse(BaseModel):
    enabled: bool
    level: str
    pii_types: list[str]
    disabled_types: list[str]
    exempt_roles: list[str]
    max_text_length: int


# ── Endpoints ────────────────────────────────────────────────────────────


def _require_cpi_admin(user: User) -> None:
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Requires cpi-admin role")


@router.post("/scan", response_model=PIIScanResponse)
async def scan_text(
    request: PIIScanRequest,
    user: User = Depends(get_current_user),
) -> PIIScanResponse:
    """Detect PII types in the provided text without masking.

    Returns a list of detected PII types and their occurrence counts.
    Useful for compliance auditing and data classification.
    """
    _require_cpi_admin(user)

    masker = get_masker()
    detected = masker.detect_only(request.text)

    detections = [PIIDetection(pii_type=pii_type.value, count=len(matches)) for pii_type, matches in detected.items()]

    return PIIScanResponse(
        detections=detections,
        total_pii_count=sum(d.count for d in detections),
        text_length=len(request.text),
    )


@router.post("/mask", response_model=PIIMaskResponse)
async def mask_text(
    request: PIIMaskRequest,
    user: User = Depends(get_current_user),
) -> PIIMaskResponse:
    """Mask PII in the provided text and return the result.

    Applies the production masking configuration. Useful for previewing
    how PII masking will transform data before enabling it on a pipeline.
    """
    _require_cpi_admin(user)

    masker = get_masker()
    detected = masker.detect_only(request.text)
    masked = masker.mask(request.text)

    detections = [PIIDetection(pii_type=pii_type.value, count=len(matches)) for pii_type, matches in detected.items()]

    return PIIMaskResponse(
        masked_text=masked,
        original_length=len(request.text),
        masked_length=len(masked),
        detections=detections,
    )


@router.get("/config", response_model=PIIConfigResponse)
async def get_config(
    user: User = Depends(get_current_user),
) -> PIIConfigResponse:
    """Return the current PII masking configuration."""
    _require_cpi_admin(user)

    config = get_masker().config

    return PIIConfigResponse(
        enabled=config.enabled,
        level=config.level.value,
        pii_types=[t.value for t in PIIType],
        disabled_types=[t.value for t in config.disabled_types],
        exempt_roles=sorted(config.exempt_roles),
        max_text_length=config.max_text_length,
    )
