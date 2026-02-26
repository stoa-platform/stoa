"""System info router — platform metadata, edition, features (CAB-1311).

Public endpoint (no auth required) — exposes non-sensitive platform info.
"""

from fastapi import APIRouter

from ..config import settings
from ..schemas.system import (
    Edition,
    LicenseInfo,
    SystemInfoResponse,
    get_features_for_edition,
)

router = APIRouter(prefix="/v1/system", tags=["System"])

# Edition is configured via STOA_EDITION env var (default: community)
_EDITION = Edition(getattr(settings, "STOA_EDITION", "community"))

_LICENSE_MAP = {
    Edition.COMMUNITY: LicenseInfo(
        edition=Edition.COMMUNITY,
        license_type="Apache-2.0",
        license_url="https://github.com/stoa-platform/stoa/blob/main/LICENSE",
    ),
    Edition.STANDARD: LicenseInfo(
        edition=Edition.STANDARD,
        license_type="Commercial",
        license_url="https://gostoa.dev/pricing",
    ),
    Edition.ENTERPRISE: LicenseInfo(
        edition=Edition.ENTERPRISE,
        license_type="Commercial",
        license_url="https://gostoa.dev/pricing",
    ),
}


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info() -> SystemInfoResponse:
    """Return platform system information.

    Public endpoint — no authentication required.
    Exposes version, edition, license, and available features.
    """
    license_info = _LICENSE_MAP.get(
        _EDITION,
        _LICENSE_MAP[Edition.COMMUNITY],
    )
    features = get_features_for_edition(_EDITION)

    return SystemInfoResponse(
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        license=license_info,
        features=features,
    )
