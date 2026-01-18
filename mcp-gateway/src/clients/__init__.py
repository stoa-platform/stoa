"""HTTP clients for external API calls.

This module provides clients for calling external APIs,
implementing ADR-001 compliance (no direct database access).
"""
from .core_api_client import (
    CoreAPIClient,
    get_core_api_client,
    init_core_api_client,
    shutdown_core_api_client,
)

__all__ = [
    "CoreAPIClient",
    "get_core_api_client",
    "init_core_api_client",
    "shutdown_core_api_client",
]
