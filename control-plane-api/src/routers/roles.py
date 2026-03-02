"""Role taxonomy and metadata endpoint (CAB-1634).

Exposes all RBAC roles with human-readable display names, descriptions,
permissions, and alias relationships.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.dependencies import User, get_current_user
from ..auth.rbac import ROLE_ALIASES, ROLE_METADATA, ROLE_PERMISSIONS

router = APIRouter(prefix="/v1", tags=["Roles"])


class RoleDetail(BaseModel):
    """Single role with metadata and permissions."""

    name: str
    display_name: str
    description: str
    scope: str
    category: str
    permissions: list[str]
    inherits_from: str | None = None


class RolesResponse(BaseModel):
    """All roles with metadata."""

    roles: list[RoleDetail]
    aliases: dict[str, str]


@router.get(
    "/roles",
    response_model=RolesResponse,
    summary="List all roles with metadata and permissions",
)
async def list_roles(
    _user: User = Depends(get_current_user),
) -> RolesResponse:
    roles = []
    for role_name, meta in ROLE_METADATA.items():
        # Get permissions: for aliases, resolve to core role first
        if meta.get("inherits_from"):
            perms = ROLE_PERMISSIONS.get(meta["inherits_from"], [])
        else:
            perms = ROLE_PERMISSIONS.get(role_name, [])

        roles.append(
            RoleDetail(
                name=role_name,
                display_name=meta["display_name"],
                description=meta["description"],
                scope=meta["scope"],
                category=meta["category"],
                permissions=sorted(perms),
                inherits_from=meta.get("inherits_from"),
            )
        )

    return RolesResponse(roles=roles, aliases=ROLE_ALIASES)
