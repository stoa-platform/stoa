"""Demo tenant management API router.

Provides endpoints to seed, reset, and check the demo tenant environment.
All endpoints require cpi-admin role.

Routes:
- GET  /v1/demo/status  — Check demo tenant state
- POST /v1/demo/seed    — Seed demo tenant (idempotent)
- POST /v1/demo/reset   — Reset demo tenant (delete + re-seed)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User
from ..auth.rbac import require_role
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/demo", tags=["Demo"])


class DemoStatusResponse(BaseModel):
    """Demo tenant status."""

    exists: bool
    tenants: int = 0
    mcp_servers: int = 0
    tools: int = 0
    consumers: int = 0
    subscriptions: int = 0
    catalog_apis: int = 0


class DemoSeedResponse(BaseModel):
    """Demo seed result."""

    action: str
    tenant_created: int = 0
    servers_created: int = 0
    tools_created: int = 0
    consumers_created: int = 0
    subscriptions_created: int = 0
    catalog_apis_created: int = 0
    message: str = ""


@router.get("/status", response_model=DemoStatusResponse)
async def get_demo_status(
    _user: User = Depends(require_role(["cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> DemoStatusResponse:
    """Check current demo tenant state."""
    from scripts.seed_demo_tenant import check_demo_state

    counts = await check_demo_state(db)
    return DemoStatusResponse(
        exists=counts.get("tenants", 0) > 0,
        tenants=max(counts.get("tenants", 0), 0),
        mcp_servers=max(counts.get("mcp_servers", 0), 0),
        tools=max(counts.get("mcp_server_tools", 0), 0),
        consumers=max(counts.get("consumers", 0), 0),
        subscriptions=max(counts.get("mcp_server_subscriptions", 0), 0),
        catalog_apis=max(counts.get("api_catalog", 0), 0),
    )


@router.post("/seed", response_model=DemoSeedResponse)
async def seed_demo(
    _user: User = Depends(require_role(["cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> DemoSeedResponse:
    """Seed the demo tenant with sample data (idempotent)."""
    from scripts.seed_demo_tenant import check_demo_state, seed_demo_tenant

    counts = await check_demo_state(db)
    if counts.get("tenants", 0) > 0:
        return DemoSeedResponse(
            action="skipped",
            message="Demo tenant already exists. Use POST /v1/demo/reset to re-seed.",
        )

    try:
        summary = await seed_demo_tenant(db)
        return DemoSeedResponse(
            action="seeded",
            tenant_created=summary["tenant"],
            servers_created=summary["servers"],
            tools_created=summary["tools"],
            consumers_created=summary["consumers"],
            subscriptions_created=summary["subscriptions"],
            catalog_apis_created=summary["catalog"],
            message="Demo tenant seeded successfully.",
        )
    except Exception as e:
        logger.exception("Failed to seed demo tenant")
        raise HTTPException(status_code=500, detail=f"Seed failed: {e}") from e


@router.post("/reset", response_model=DemoSeedResponse)
async def reset_demo(
    _user: User = Depends(require_role(["cpi-admin"])),
    db: AsyncSession = Depends(get_db),
) -> DemoSeedResponse:
    """Reset demo tenant — delete all demo data and re-seed."""
    from scripts.seed_demo_tenant import delete_demo_data, seed_demo_tenant

    try:
        deleted = await delete_demo_data(db)
        logger.info("Demo tenant reset: deleted %d rows", deleted)

        summary = await seed_demo_tenant(db)
        return DemoSeedResponse(
            action="reset",
            tenant_created=summary["tenant"],
            servers_created=summary["servers"],
            tools_created=summary["tools"],
            consumers_created=summary["consumers"],
            subscriptions_created=summary["subscriptions"],
            catalog_apis_created=summary["catalog"],
            message=f"Demo tenant reset: deleted {deleted} rows, re-seeded.",
        )
    except Exception as e:
        logger.exception("Failed to reset demo tenant")
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}") from e
