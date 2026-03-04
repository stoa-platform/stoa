"""Environments router — ADR-040 Born GitOps multi-environment support

Serves environment registry with connection URLs for Console/Portal
multi-backend switching (CAB-1659).
"""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/environments", tags=["Environments"])


EnvironmentMode = Literal["full", "read-only", "promote-only"]


class PublicEnvironmentSummary(BaseModel):
    """Public-safe environment info — no auth URLs exposed."""

    name: str
    label: str
    mode: EnvironmentMode
    color: str
    health_url: str


class PublicEnvironmentsResponse(BaseModel):
    environments: list[PublicEnvironmentSummary]
    current: str


class EnvironmentEndpoints(BaseModel):
    """Connection URLs for a specific environment."""

    api_url: str
    keycloak_url: str
    keycloak_realm: str
    mcp_url: str


class EnvironmentConfig(BaseModel):
    name: str
    label: str
    mode: EnvironmentMode
    color: str
    endpoints: EnvironmentEndpoints | None = None
    is_current: bool = False


class EnvironmentListResponse(BaseModel):
    environments: list[EnvironmentConfig]
    current: str


def _build_default_environments() -> list[EnvironmentConfig]:
    """Build environment list from settings.

    The current environment is always included. Additional environments
    are loaded from STOA_ENVIRONMENTS JSON config if set.
    """
    base = settings.BASE_DOMAIN
    current_env = settings.ENVIRONMENT

    # Default environments based on domain convention
    defaults: list[EnvironmentConfig] = [
        EnvironmentConfig(
            name="production",
            label="Production",
            mode="read-only",
            color="#ef4444",
            endpoints=EnvironmentEndpoints(
                api_url=f"https://api.{base}",
                keycloak_url=f"https://auth.{base}",
                keycloak_realm="stoa",
                mcp_url=f"https://mcp.{base}",
            ),
            is_current=(current_env == "production"),
        ),
        EnvironmentConfig(
            name="staging",
            label="Staging",
            mode="full",
            color="#f59e0b",
            endpoints=EnvironmentEndpoints(
                api_url=f"https://staging-api.{base}",
                keycloak_url=f"https://staging-auth.{base}",
                keycloak_realm="stoa",
                mcp_url=f"https://staging-mcp.{base}",
            ),
            is_current=(current_env == "staging"),
        ),
        EnvironmentConfig(
            name="dev",
            label="Development",
            mode="full",
            color="#22c55e",
            endpoints=EnvironmentEndpoints(
                api_url=f"https://dev-api.{base}",
                keycloak_url=f"https://dev-auth.{base}",
                keycloak_realm="stoa",
                mcp_url=f"https://dev-mcp.{base}",
            ),
            is_current=(current_env == "dev"),
        ),
    ]

    # Override with custom environments from JSON config
    custom_json = getattr(settings, "STOA_ENVIRONMENTS", "")
    if custom_json:
        try:
            custom_envs = json.loads(custom_json)
            if isinstance(custom_envs, list):
                return [EnvironmentConfig(**env) for env in custom_envs]
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to parse STOA_ENVIRONMENTS", error=str(e))

    return defaults


@router.get("/public", response_model=PublicEnvironmentsResponse)
async def list_public_environments() -> PublicEnvironmentsResponse:
    """List environments with public-safe info only.

    No authentication required. Exposes only health URLs — no keycloak
    or MCP URLs. Intended for monitoring CronJobs and status dashboards.
    """
    envs = _build_default_environments()
    current = next((e.name for e in envs if e.is_current), settings.ENVIRONMENT)
    return PublicEnvironmentsResponse(
        environments=[
            PublicEnvironmentSummary(
                name=e.name,
                label=e.label,
                mode=e.mode,
                color=e.color,
                health_url=f"{e.endpoints.api_url}/health" if e.endpoints else "",
            )
            for e in envs
        ],
        current=current,
    )


@router.get("", response_model=EnvironmentListResponse)
async def list_environments(
    user: User = Depends(get_current_user),
) -> EnvironmentListResponse:
    """List available environments with connection URLs.

    Returns environment configs including API/Keycloak/MCP endpoints
    for Console and Portal multi-backend switching.
    """
    envs = _build_default_environments()
    current = next((e.name for e in envs if e.is_current), settings.ENVIRONMENT)
    return EnvironmentListResponse(environments=envs, current=current)
