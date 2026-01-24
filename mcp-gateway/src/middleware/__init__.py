"""Middleware components."""

from .auth import (
    TokenClaims,
    OIDCAuthenticator,
    get_current_user,
    get_optional_user,
    require_role,
    require_scope,
)
from .metrics import (
    MetricsMiddleware,
    record_tool_invocation,
    record_auth_attempt,
    record_backend_request,
    update_tools_registered,
)
from .shadow import ShadowMiddleware

__all__ = [
    # Auth
    "TokenClaims",
    "OIDCAuthenticator",
    "get_current_user",
    "get_optional_user",
    "require_role",
    "require_scope",
    # Metrics
    "MetricsMiddleware",
    "record_tool_invocation",
    "record_auth_attempt",
    "record_backend_request",
    "update_tools_registered",
    # Shadow (Python → Rust Migration)
    "ShadowMiddleware",
]
