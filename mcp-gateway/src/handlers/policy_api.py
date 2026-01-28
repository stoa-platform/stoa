# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Policy Management API Endpoints.

CAB-875: Provides dry-run policy checking and rule listing for governance demos.

These endpoints allow:
- Pre-flight validation of tool arguments against policies
- Listing active policy rules for transparency
- Demo scenarios showing policy enforcement
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..middleware.auth import TokenClaims, get_current_user
from ..policy import get_argument_engine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp/v1/policies", tags=["Policy Engine"])


# =============================================================================
# Request/Response Models
# =============================================================================


class PolicyCheckRequest(BaseModel):
    """Request to check policies against a tool invocation (dry-run)."""

    tool_name: str = Field(
        ...,
        description="Name of the tool to check",
        examples=["Linear:create_issue"],
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments to validate against policies",
    )


class PolicyCheckResponse(BaseModel):
    """Response from policy dry-run check."""

    allowed: bool = Field(
        description="Whether the invocation would be allowed",
    )
    policy_name: str | None = Field(
        None,
        description="Name of matching policy (if any)",
    )
    rule_index: int | None = Field(
        None,
        description="Index of matching rule within policy",
    )
    message: str | None = Field(
        None,
        description="Policy message (violation or warning)",
    )
    action: str | None = Field(
        None,
        description="Action taken: deny, allow, or warn",
    )


class PolicyRuleInfo(BaseModel):
    """Information about a single policy rule."""

    name: str = Field(description="Policy name")
    description: str = Field(description="Human-readable description")
    tool: str = Field(description="Tool pattern (supports wildcards)")
    enabled: bool = Field(description="Whether policy is active")
    priority: int = Field(description="Evaluation priority (higher = first)")
    rules_count: int = Field(description="Number of rules in policy")


class ListPolicyRulesResponse(BaseModel):
    """Response listing all active policy rules."""

    rules: list[PolicyRuleInfo] = Field(
        default_factory=list,
        description="List of active policy rules",
    )
    total_count: int = Field(
        default=0,
        description="Total number of loaded policies",
    )
    engine_enabled: bool = Field(
        description="Whether the policy engine is enabled",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/check",
    response_model=PolicyCheckResponse,
    summary="Dry-run policy check",
    description="Check policies against a tool invocation without executing the tool.",
)
async def check_policies(
    request: PolicyCheckRequest,
    user: TokenClaims = Depends(get_current_user),
) -> PolicyCheckResponse:
    """Dry-run policy check for tool invocation.

    This endpoint validates tool arguments against all matching policies
    WITHOUT actually invoking the tool. Useful for:
    - Pre-flight validation in AI agents
    - Policy testing and debugging
    - Demo scenarios showing policy enforcement

    Returns the policy evaluation result including whether the call
    would be allowed, denied, or would trigger a warning.
    """
    engine = await get_argument_engine()

    if not engine.enabled:
        return PolicyCheckResponse(
            allowed=True,
            message="Policy engine is disabled",
        )

    result = engine.evaluate(request.tool_name, request.arguments)

    logger.info(
        "Policy dry-run check",
        tool_name=request.tool_name,
        user=user.subject if user else "anonymous",
        allowed=result.allowed,
        policy=result.policy_name,
        action=result.action,
    )

    return PolicyCheckResponse(
        allowed=result.allowed,
        policy_name=result.policy_name,
        rule_index=result.rule_index,
        message=result.message,
        action=result.action,
    )


@router.get(
    "/rules",
    response_model=ListPolicyRulesResponse,
    summary="List active policy rules",
    description="Returns all loaded policy rules with their configuration.",
)
async def list_policy_rules(
    user: TokenClaims = Depends(get_current_user),
) -> ListPolicyRulesResponse:
    """List all active policy rules.

    Returns metadata about all loaded policies including:
    - Policy name and description
    - Tool pattern for matching
    - Whether the policy is enabled
    - Evaluation priority
    - Number of rules

    This is useful for:
    - Understanding what policies are in effect
    - Debugging policy configuration
    - Demo scenarios showing governance rules
    """
    engine = await get_argument_engine()

    if not engine.enabled:
        return ListPolicyRulesResponse(
            rules=[],
            total_count=0,
            engine_enabled=False,
        )

    # Access internal _policies list (read-only)
    rules = []
    for policy in engine._policies:
        rules.append(
            PolicyRuleInfo(
                name=policy.name,
                description=policy.description,
                tool=policy.tool,
                enabled=policy.enabled,
                priority=policy.priority,
                rules_count=len(policy.rules),
            )
        )

    logger.info(
        "Listed policy rules",
        user=user.subject if user else "anonymous",
        count=len(rules),
    )

    return ListPolicyRulesResponse(
        rules=rules,
        total_count=len(rules),
        engine_enabled=True,
    )
