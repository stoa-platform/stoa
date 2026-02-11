"""Middleware components."""

from .auth import (
    OIDCAuthenticator,
    TokenClaims,
    get_current_user,
    get_optional_user,
    require_role,
    require_scope,
)
from .cache_middleware import SemanticCacheMiddleware
from .metrics import (
    MetricsMiddleware,
    record_auth_attempt,
    record_backend_request,
    record_tool_invocation,
    update_tools_registered,
)
from .response_transformer import ResponseTransformerMiddleware
from .shadow import ShadowMiddleware
from .token_counter import TokenCounterMiddleware
from .token_counter_worker import token_counter_worker

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
    # Token Optimization (CAB-881)
    "TokenCounterMiddleware",
    "token_counter_worker",
    # Response Transformer (CAB-881 Step 2)
    "ResponseTransformerMiddleware",
    # Semantic Cache (CAB-881 Step 4)
    "SemanticCacheMiddleware",
]
