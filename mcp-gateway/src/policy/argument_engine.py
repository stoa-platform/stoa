"""Argument-based Policy Engine for tool invocation validation.

CAB-876: Validates tool arguments against YAML-defined business rules
before execution. This is separate from OPA scope-based RBAC.

The OPA engine controls WHO can call tools (RBAC).
This engine controls WHAT argument values are allowed (business rules).
"""

import fnmatch
import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from ..config import get_settings
from .argument_models import (
    Policy,
    PolicyFile,
    PolicyResult,
    ConditionLeaf,
    ConditionGroup,
    Operator,
)

logger = structlog.get_logger(__name__)


class ArgumentPolicyEngine:
    """Engine for evaluating argument-based policies.

    Loads policies from YAML files and evaluates tool arguments
    against defined rules before execution.

    Policies are evaluated in priority order (highest first).
    First matching deny/allow rule wins.

    Example usage:
        engine = ArgumentPolicyEngine()
        await engine.startup()

        result = engine.evaluate("Linear:create_issue", {
            "priority": 1,
            "cycle": None
        })

        if not result.allowed:
            raise PolicyViolationError(result.policy_name, result.message)
    """

    def __init__(self, policy_path: str | None = None) -> None:
        """Initialize the engine.

        Args:
            policy_path: Path to directory containing YAML policy files.
                        Defaults to settings.argument_policy_path.
        """
        settings = get_settings()
        self._enabled = settings.argument_policy_enabled
        self._fail_closed = settings.argument_policy_fail_closed
        self._policy_path = Path(policy_path or settings.argument_policy_path)
        self._policies: list[Policy] = []
        self._load_error: str | None = None

    async def startup(self) -> None:
        """Load policies on application startup."""
        if not self._enabled:
            logger.info("Argument policy engine disabled")
            return

        await self.reload()

    async def shutdown(self) -> None:
        """Cleanup on application shutdown."""
        self._policies.clear()
        logger.info("Argument policy engine shutdown")

    async def reload(self) -> bool:
        """Reload policies from disk.

        Returns:
            True if reload succeeded, False on error.
        """
        self._policies.clear()
        self._load_error = None

        if not self._policy_path.exists():
            logger.warning(
                "Policy directory does not exist",
                path=str(self._policy_path),
            )
            return True  # Empty policies is valid

        try:
            for yaml_file in self._policy_path.glob("*.yaml"):
                await self._load_file(yaml_file)

            # Sort by priority (highest first)
            self._policies.sort(key=lambda p: -p.priority)

            logger.info(
                "Loaded argument policies",
                count=len(self._policies),
                path=str(self._policy_path),
                policies=[p.name for p in self._policies],
            )
            return True

        except Exception as e:
            self._load_error = str(e)
            logger.error("Failed to load argument policies", error=str(e))
            return False

    async def _load_file(self, path: Path) -> None:
        """Load policies from a single YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return

        policy_file = PolicyFile.model_validate(data)

        for policy in policy_file.policies:
            if policy.enabled:
                self._policies.append(policy)
                logger.debug(
                    "Loaded policy",
                    name=policy.name,
                    tool=policy.tool,
                    rules=len(policy.rules),
                    file=path.name,
                )

    @property
    def enabled(self) -> bool:
        """Check if the engine is enabled."""
        return self._enabled

    @property
    def policy_count(self) -> int:
        """Return number of loaded policies."""
        return len(self._policies)

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PolicyResult:
        """Evaluate policies for a tool invocation.

        Args:
            tool_name: Name of the tool being invoked
            arguments: Arguments passed to the tool

        Returns:
            PolicyResult indicating whether invocation is allowed
        """
        if not self._enabled:
            return PolicyResult(allowed=True)

        # Fail-closed if load error occurred
        if self._load_error and self._fail_closed:
            logger.warning(
                "Policy evaluation blocked due to load error",
                tool_name=tool_name,
                error=self._load_error,
            )
            return PolicyResult(
                allowed=False,
                message=f"Policy engine error: {self._load_error}",
            )

        # Find matching policies
        matching_policies = self._find_matching_policies(tool_name)

        if not matching_policies:
            logger.debug(
                "No matching policies for tool",
                tool_name=tool_name,
            )
            return PolicyResult(allowed=True)

        # Evaluate each policy's rules
        for policy in matching_policies:
            result = self._evaluate_policy(policy, arguments)

            if result.action == "deny":
                logger.warning(
                    "Policy violation",
                    tool_name=tool_name,
                    policy=policy.name,
                    message=result.message,
                    arguments=arguments,
                )
                return result

            if result.action == "allow":
                logger.info(
                    "Policy explicitly allowed",
                    tool_name=tool_name,
                    policy=policy.name,
                )
                return result

            if result.action == "warn":
                logger.warning(
                    "Policy warning (allowed)",
                    tool_name=tool_name,
                    policy=policy.name,
                    message=result.message,
                )
                # Continue evaluation (warn doesn't stop)

        # No deny/allow rule matched
        logger.info(
            "Policy evaluation passed",
            tool_name=tool_name,
            checked_policies=[p.name for p in matching_policies],
        )
        return PolicyResult(allowed=True)

    def _find_matching_policies(self, tool_name: str) -> list[Policy]:
        """Find policies that match the tool name.

        Supports exact match and wildcard patterns (fnmatch).
        Examples:
            - "Linear:create_issue" matches "Linear:create_issue"
            - "Linear:*" matches "Linear:create_issue"
            - "*:create_*" matches "Linear:create_issue"
        """
        matching = []
        for policy in self._policies:
            if fnmatch.fnmatch(tool_name, policy.tool):
                matching.append(policy)
        return matching

    def _evaluate_policy(
        self,
        policy: Policy,
        arguments: dict[str, Any],
    ) -> PolicyResult:
        """Evaluate a single policy's rules against arguments."""
        for idx, rule in enumerate(policy.rules):
            if self._evaluate_condition(rule.condition, arguments):
                return PolicyResult(
                    allowed=(rule.action == "allow"),
                    policy_name=policy.name,
                    rule_index=idx,
                    message=rule.message,
                    action=rule.action,
                )

        return PolicyResult(allowed=True)

    def _evaluate_condition(
        self,
        condition: ConditionLeaf | ConditionGroup,
        arguments: dict[str, Any],
    ) -> bool:
        """Evaluate a condition against arguments."""
        if isinstance(condition, ConditionLeaf):
            return self._evaluate_leaf(condition, arguments)

        # ConditionGroup
        if condition.all:
            return all(
                self._evaluate_condition(c, arguments) for c in condition.all
            )
        if condition.any:
            return any(
                self._evaluate_condition(c, arguments) for c in condition.any
            )

        return False

    def _evaluate_leaf(
        self,
        condition: ConditionLeaf,
        arguments: dict[str, Any],
    ) -> bool:
        """Evaluate a single leaf condition."""
        # Get field value (supports nested paths like "user.email")
        # Returns None for both null values AND absent keys
        value = self._get_field_value(condition.field, arguments)

        op = condition.operator
        expected = condition.value

        # Null checks (handles both null values and absent keys)
        if op == Operator.IS_NULL:
            return value is None
        if op == Operator.NOT_NULL:
            return value is not None

        # If value is None for other operators, condition doesn't match
        if value is None:
            return False

        # Equality operators
        if op == Operator.EQ:
            return value == expected
        if op == Operator.NE:
            return value != expected

        # List membership
        if op == Operator.IN:
            return value in expected
        if op == Operator.NOT_IN:
            return value not in expected

        # Numeric comparisons
        if op == Operator.GT:
            return value > expected
        if op == Operator.GTE:
            return value >= expected
        if op == Operator.LT:
            return value < expected
        if op == Operator.LTE:
            return value <= expected

        # String operations
        if op == Operator.REGEX:
            try:
                return bool(re.match(expected, str(value)))
            except re.error:
                logger.warning("Invalid regex pattern", pattern=expected)
                return False
        if op == Operator.CONTAINS:
            return expected in str(value)

        return False

    def _get_field_value(
        self,
        field_path: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Get a field value from arguments, supporting nested paths.

        Uses .get() to return None for both:
        - Explicitly null values: {"field": null}
        - Absent keys: {} (field not present)

        This ensures is_null operator handles both cases identically.
        """
        parts = field_path.split(".")
        current: Any = arguments

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)  # Returns None if key absent
            else:
                return None

        return current


# =============================================================================
# Singleton Management
# =============================================================================

_argument_engine: ArgumentPolicyEngine | None = None


async def get_argument_engine() -> ArgumentPolicyEngine:
    """Get the argument policy engine singleton."""
    global _argument_engine
    if _argument_engine is None:
        _argument_engine = ArgumentPolicyEngine()
        await _argument_engine.startup()
    return _argument_engine


async def shutdown_argument_engine() -> None:
    """Shutdown the argument policy engine."""
    global _argument_engine
    if _argument_engine:
        await _argument_engine.shutdown()
        _argument_engine = None
