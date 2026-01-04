"""Policy engine module."""

from .opa_client import (
    OPAClient,
    PolicyDecision,
    get_opa_client,
    shutdown_opa_client,
)

__all__ = [
    "OPAClient",
    "PolicyDecision",
    "get_opa_client",
    "shutdown_opa_client",
]
