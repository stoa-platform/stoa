"""Environments router — ADR-040 Born GitOps multi-environment support"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import User, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/environments", tags=["Environments"])


EnvironmentMode = Literal["full", "read-only", "promote-only"]


class EnvironmentConfig(BaseModel):
    name: str
    label: str
    mode: EnvironmentMode
    color: str


class EnvironmentListResponse(BaseModel):
    environments: list[EnvironmentConfig]


# Default environment configurations
# In the future, these will be loaded from the database per tenant.
DEFAULT_ENVIRONMENTS: list[EnvironmentConfig] = [
    EnvironmentConfig(name="dev", label="Development", mode="full", color="green"),
    EnvironmentConfig(name="staging", label="Staging", mode="full", color="amber"),
    EnvironmentConfig(name="prod", label="Production", mode="read-only", color="red"),
]


@router.get("", response_model=EnvironmentListResponse)
async def list_environments(
    user: User = Depends(get_current_user),
) -> EnvironmentListResponse:
    """List available environments with their configuration.

    Returns environment configs including mode (full, read-only, promote-only)
    which determines what actions are allowed in each environment.
    """
    return EnvironmentListResponse(environments=DEFAULT_ENVIRONMENTS)
