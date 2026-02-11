"""Environment write guard — ADR-040 Born GitOps

Blocks write operations (POST/PUT/DELETE) in read-only environments.
cpi-admin can override for emergency hotfixes.
"""

import logging
from typing import Literal

from fastapi import Depends, HTTPException, Query

from .dependencies import User, get_current_user

logger = logging.getLogger(__name__)

# Environment modes — mirrors environments.py defaults
ENVIRONMENT_MODES: dict[str, Literal["full", "read-only", "promote-only"]] = {
    "dev": "full",
    "staging": "full",
    "prod": "read-only",
}


def require_writable_environment(
    environment: str | None = Query(default=None, description="Target environment"),
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that blocks writes in read-only environments.

    Usage:
        @router.post("")
        async def create_api(user: User = Depends(require_writable_environment)):
            ...
    """
    if not environment:
        return user

    mode = ENVIRONMENT_MODES.get(environment, "full")

    if mode == "read-only" and "cpi-admin" not in user.roles:
        logger.warning(
            "Write blocked in read-only environment",
            environment=environment,
            user_id=user.id,
            username=user.username,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Environment '{environment}' is read-only. Only cpi-admin can perform writes.",
        )

    return user
