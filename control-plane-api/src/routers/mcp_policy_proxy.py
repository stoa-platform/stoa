"""MCP Gateway Policy Proxy Router.

CAB-875: Proxies policy management requests to the MCP Gateway.
Follows the same pattern as mcp_proxy.py for consistency.

Endpoints:
- POST /v1/mcp/policies/check - Dry-run policy validation
- GET /v1/mcp/policies/rules - List active policy rules
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ..auth import get_current_user, User
from .mcp_proxy import proxy_to_mcp

# Security scheme for extracting Bearer token
security = HTTPBearer()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mcp/policies", tags=["MCP Policy Engine"])


# =============================================================================
# Request/Response Models (mirror MCP Gateway models)
# =============================================================================


class PolicyCheckRequest(BaseModel):
    """Request to check policies against a tool invocation."""

    tool_name: str = Field(
        ...,
        description="Name of the tool to check",
        examples=["Linear:create_issue"],
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments to validate",
    )


class PolicyCheckResponse(BaseModel):
    """Response from policy dry-run check."""

    allowed: bool
    policy_name: str | None = None
    rule_index: int | None = None
    message: str | None = None
    action: str | None = None


class PolicyRuleInfo(BaseModel):
    """Information about a policy rule."""

    name: str
    description: str
    tool: str
    enabled: bool
    priority: int
    rules_count: int


class ListPolicyRulesResponse(BaseModel):
    """Response listing active policy rules."""

    rules: list[PolicyRuleInfo]
    total_count: int
    engine_enabled: bool


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/check", response_model=PolicyCheckResponse)
async def check_policies(
    request: PolicyCheckRequest,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Dry-run policy check for tool invocation.

    Validates arguments against all matching policies without executing the tool.
    Proxies to MCP Gateway.

    Use cases:
    - Pre-flight validation in AI agents
    - Policy testing and debugging
    - Demo scenarios showing STOA governance
    """
    result = await proxy_to_mcp(
        "POST",
        "/mcp/v1/policies/check",
        user,
        credentials.credentials,
        json_body={
            "tool_name": request.tool_name,
            "arguments": request.arguments,
        },
    )
    return result


@router.get("/rules", response_model=ListPolicyRulesResponse)
async def list_policy_rules(
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    List all active policy rules.

    Returns metadata about loaded policies including name, tool pattern,
    priority, and enabled status. Proxies to MCP Gateway.

    Use cases:
    - Understanding what policies are in effect
    - Debugging policy configuration
    - Demo scenarios showing governance rules
    """
    result = await proxy_to_mcp(
        "GET",
        "/mcp/v1/policies/rules",
        user,
        credentials.credentials,
    )
    return result
