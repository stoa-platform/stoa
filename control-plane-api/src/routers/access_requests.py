"""Public endpoint for portal email capture.

No authentication required — this is the first touchpoint
for unauthenticated visitors on the Developer Portal.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from src.database import get_db
from src.models.access_request import AccessRequest
from src.schemas.access_request import AccessRequestCreate, AccessRequestResponse

router = APIRouter(prefix="/v1/access-requests", tags=["Access Requests"])


@router.post(
    "",
    response_model=AccessRequestResponse,
    responses={200: {"description": "Email already registered"}, 201: {"description": "New request created"}},
)
async def create_access_request(
    payload: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Submit an access request (public, no auth).

    Idempotent: returns 200 if email already exists, 201 if new.
    """
    result = await db.execute(select(AccessRequest).where(AccessRequest.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing:
        return JSONResponse(
            status_code=200,
            content=AccessRequestResponse(
                message="Thank you! We'll reach out shortly.",
                request_id=existing.id,
            ).model_dump(mode="json"),
        )

    access_request = AccessRequest(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        company=payload.company,
        role=payload.role,
        source=payload.source,
    )
    db.add(access_request)
    await db.flush()

    return JSONResponse(
        status_code=201,
        content=AccessRequestResponse(
            message="Thank you! We'll reach out shortly.",
            request_id=access_request.id,
        ).model_dump(mode="json"),
    )
