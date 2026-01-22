"""Deprecation management mixin.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-605 Phase 3: Deprecation layer for backward compatibility.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import structlog

from ...models import AnyTool
from ...tools import DEPRECATION_MAPPINGS
from .exceptions import ToolNotFoundError
from .models import DeprecatedToolAlias

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class DeprecationMixin:
    """Mixin providing deprecation management methods.

    Requires LookupMixin to be in the inheritance chain for get() method.
    """

    # Type hints for attributes from ToolRegistry
    _deprecated_aliases: dict[str, DeprecatedToolAlias]

    # Type hint for method from LookupMixin (resolved via MRO)
    # Note: Do NOT define a stub method here - it would shadow LookupMixin.get()
    get: Any  # Callable[[str, str | None], AnyTool | None] from LookupMixin

    async def _register_deprecation_aliases(self) -> None:
        """Register deprecation aliases for legacy tool names.

        CAB-605 Phase 3: Maps old tool names to new consolidated tools
        with appropriate action parameters.
        """
        for old_name, (new_name, new_args) in DEPRECATION_MAPPINGS.items():
            self.register_deprecation(old_name, new_name, new_args)
        logger.info(
            "Registered deprecation aliases",
            count=len(self._deprecated_aliases),
        )

    def register_deprecation(
        self,
        old_name: str,
        new_name: str,
        new_args: dict[str, Any] | None = None,
        deprecation_days: int = 60,
    ) -> None:
        """Register a deprecated tool alias for backward compatibility.

        CAB-605: When consolidating tools, register deprecations to maintain
        backward compatibility. Clients calling the old tool name will be
        redirected to the new tool with appropriate arguments.

        Args:
            old_name: The deprecated tool name
            new_name: The replacement tool name
            new_args: Arguments to inject (e.g., {"action": "list"})
            deprecation_days: Days until the alias expires (default: 60)
        """
        now = datetime.now(timezone.utc)
        alias = DeprecatedToolAlias(
            old_name=old_name,
            new_name=new_name,
            new_args=new_args or {},
            deprecated_at=now,
            remove_after=now + timedelta(days=deprecation_days),
        )
        self._deprecated_aliases[old_name] = alias
        logger.info(
            "Registered deprecation alias",
            old_name=old_name,
            new_name=new_name,
            new_args=new_args,
            remove_after=alias.remove_after.isoformat(),
        )

    def resolve_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tenant_id: str | None = None,
    ) -> tuple[AnyTool, dict[str, Any], bool]:
        """Resolve tool name, handling deprecations.

        CAB-605 Phase 3: Checks for deprecated aliases and redirects to
        new tools while logging deprecation warnings.

        Args:
            name: Tool name (may be deprecated)
            arguments: Original arguments from client
            tenant_id: Tenant context for tool lookup

        Returns:
            Tuple of (tool, merged_arguments, is_deprecated)

        Raises:
            ToolNotFoundError: If tool not found or deprecation expired
        """
        # Check for deprecated alias first
        if name in self._deprecated_aliases:
            alias = self._deprecated_aliases[name]

            # Check if past removal date
            if alias.is_expired():
                raise ToolNotFoundError(
                    f"Tool '{name}' has been removed. "
                    f"Use '{alias.new_name}' instead."
                )

            # Log deprecation warning
            days_left = alias.days_until_removal()
            logger.warning(
                "Deprecated tool called",
                old_name=name,
                new_name=alias.new_name,
                days_until_removal=days_left,
                deprecated_at=alias.deprecated_at.isoformat(),
            )

            # Merge arguments (alias args first, client args override)
            merged_args = {**alias.new_args, **arguments}

            # Lookup the new tool
            tool = self.get(alias.new_name, tenant_id)
            if not tool:
                raise ToolNotFoundError(
                    f"Replacement tool '{alias.new_name}' not found"
                )

            return tool, merged_args, True

        # Normal lookup
        tool = self.get(name, tenant_id)
        if not tool:
            raise ToolNotFoundError(f"Tool '{name}' not found")

        return tool, arguments, False

    def list_deprecated_tools(self) -> list[dict[str, Any]]:
        """List all deprecated tool aliases.

        Returns:
            List of deprecation information dictionaries
        """
        return [
            {
                "old_name": alias.old_name,
                "new_name": alias.new_name,
                "new_args": alias.new_args,
                "deprecated_at": alias.deprecated_at.isoformat(),
                "remove_after": alias.remove_after.isoformat(),
                "days_until_removal": alias.days_until_removal(),
                "is_expired": alias.is_expired(),
            }
            for alias in self._deprecated_aliases.values()
        ]

    def clear_expired_deprecations(self) -> int:
        """Remove expired deprecation aliases.

        Returns:
            Number of aliases removed
        """
        expired = [
            name for name, alias in self._deprecated_aliases.items()
            if alias.is_expired()
        ]
        for name in expired:
            del self._deprecated_aliases[name]
            logger.info("Removed expired deprecation alias", old_name=name)
        return len(expired)
