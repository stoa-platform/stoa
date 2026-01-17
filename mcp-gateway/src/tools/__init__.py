"""STOA Core Tools package.

This package contains the 35 built-in STOA platform tools organized by domain:
- Platform & Discovery (6 tools)
- API Catalog (8 tools)
- Subscriptions & Access (6 tools)
- Observability & Metrics (8 tools)
- UAC Contracts (4 tools)
- Security & Compliance (3 tools)

Core tools follow the naming convention: stoa_{domain}_{action}
"""

from .core_tools import (
    CORE_TOOLS,
    CORE_TOOLS_BY_DOMAIN,
    CORE_TOOLS_BY_NAME,
    get_core_tool,
    get_core_tools_by_domain,
    list_all_core_tools,
)

__all__ = [
    "CORE_TOOLS",
    "CORE_TOOLS_BY_DOMAIN",
    "CORE_TOOLS_BY_NAME",
    "get_core_tool",
    "get_core_tools_by_domain",
    "list_all_core_tools",
]
