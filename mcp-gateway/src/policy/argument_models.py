"""Pydantic models for YAML-based argument policy schema.

CAB-876: Models for validating tool call arguments against business rules.
This is separate from OPA scope-based RBAC.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Operator(str, Enum):
    """Supported condition operators for argument validation."""

    # Equality
    EQ = "eq"  # Equals
    NE = "ne"  # Not equals

    # List membership
    IN = "in"  # Value in list
    NOT_IN = "not_in"  # Value not in list

    # Null checks (handles both null values AND absent keys)
    IS_NULL = "is_null"  # Value is None or key absent
    NOT_NULL = "not_null"  # Value is not None and key present

    # Numeric comparisons
    GT = "gt"  # Greater than
    GTE = "gte"  # Greater than or equal
    LT = "lt"  # Less than
    LTE = "lte"  # Less than or equal

    # String operations
    REGEX = "regex"  # Regex match
    CONTAINS = "contains"  # String contains substring


class ConditionLeaf(BaseModel):
    """A single condition check on a field.

    Examples:
        - field: "priority", operator: "in", value: [1, 2]
        - field: "cycle", operator: "is_null"
        - field: "user.role", operator: "eq", value: "admin"
    """

    field: str = Field(
        ...,
        description="Field path in arguments (supports nested: 'user.email')",
        examples=["priority", "cycle", "user.role"],
    )
    operator: Operator = Field(
        ...,
        description="Comparison operator",
    )
    value: Any = Field(
        None,
        description="Value to compare against (not needed for is_null/not_null)",
    )


class ConditionGroup(BaseModel):
    """A group of conditions combined with all (AND) or any (OR).

    Only one of 'all' or 'any' should be set.

    Examples:
        - all: [condition1, condition2]  # Both must match
        - any: [condition1, condition2]  # At least one must match
    """

    all: list["ConditionLeaf | ConditionGroup"] | None = Field(
        None,
        description="All conditions must match (AND)",
    )
    any: list["ConditionLeaf | ConditionGroup"] | None = Field(
        None,
        description="At least one condition must match (OR)",
    )

    @model_validator(mode="after")
    def validate_exclusive(self) -> "ConditionGroup":
        """Ensure only 'all' or 'any' is set, not both."""
        if self.all is not None and self.any is not None:
            raise ValueError("Cannot specify both 'all' and 'any' in a condition group")
        if self.all is None and self.any is None:
            raise ValueError("Must specify either 'all' or 'any' in a condition group")
        return self


class Rule(BaseModel):
    """A single policy rule with condition and action.

    When the condition matches:
    - deny: Block the request with the message
    - allow: Explicitly allow (short-circuit other rules)
    - warn: Log a warning but allow the request
    """

    condition: ConditionLeaf | ConditionGroup = Field(
        ...,
        description="Condition to evaluate against tool arguments",
    )
    action: Literal["deny", "allow", "warn"] = Field(
        "deny",
        description="Action to take if condition matches",
    )
    message: str = Field(
        ...,
        description="Message to return on violation or log on warn",
    )


class Policy(BaseModel):
    """A complete argument validation policy.

    Policies are matched by tool name pattern (supports wildcards via fnmatch).
    Rules are evaluated in order; first matching rule determines outcome.
    """

    name: str = Field(
        ...,
        description="Unique policy identifier",
        examples=["marchemalo-cycle-required"],
    )
    description: str = Field(
        "",
        description="Human-readable description of the policy",
    )
    tool: str = Field(
        ...,
        description="Tool name pattern (supports wildcards: 'Linear:*', '*:create_*')",
        examples=["Linear:create_issue", "GitHub:*", "*:delete_*"],
    )
    enabled: bool = Field(
        True,
        description="Whether this policy is active",
    )
    priority: int = Field(
        0,
        description="Higher priority policies are evaluated first (default: 0)",
    )
    rules: list[Rule] = Field(
        ...,
        description="List of rules to evaluate in order",
        min_length=1,
    )


class PolicyFile(BaseModel):
    """Root model for a YAML policy file.

    Example YAML:
        policies:
          - name: my-policy
            tool: "MyTool:action"
            rules:
              - condition:
                  field: "status"
                  operator: "eq"
                  value: "blocked"
                action: "deny"
                message: "Blocked status not allowed"
    """

    policies: list[Policy] = Field(
        default_factory=list,
        description="List of policies defined in this file",
    )


class PolicyResult(BaseModel):
    """Result of policy evaluation.

    Returned by ArgumentPolicyEngine.evaluate().
    """

    allowed: bool = Field(
        True,
        description="Whether the invocation is allowed",
    )
    policy_name: str | None = Field(
        None,
        description="Name of policy that matched (if any)",
    )
    rule_index: int | None = Field(
        None,
        description="Index of rule that matched within the policy",
    )
    message: str | None = Field(
        None,
        description="Violation message if denied, or warn message",
    )
    action: Literal["deny", "allow", "warn"] | None = Field(
        None,
        description="Action taken by the matching rule",
    )


# Enable forward references for recursive models
ConditionGroup.model_rebuild()
