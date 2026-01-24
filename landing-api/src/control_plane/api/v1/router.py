"""API v1 router assembly."""

from fastapi import APIRouter

from control_plane.api.v1 import events, invites, welcome

# Create main v1 router
router = APIRouter(prefix="/api/v1")

# Include sub-routers
router.include_router(invites.router)
router.include_router(events.router)

# Welcome router is at root level (no /api/v1 prefix)
welcome_router = welcome.router
