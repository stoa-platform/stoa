"""
Rate Limiting Middleware for Control-Plane API (CAB-298)

MVP implementation using slowapi with in-memory storage.
Designed for evolution to distributed Redis backend (CAB-459).

Rate limit tiers:
- Authenticated users: 100 req/min
- API key users: 200 req/min
- Anonymous/IP: 30 req/min
- Tool invocations: 60 req/min (more restrictive)
"""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = structlog.get_logger(__name__)


# =============================================================================
# Rate Limit Key Functions
# =============================================================================


def get_rate_limit_key(request: Request) -> str:
    """
    Generate rate limit key based on authentication context.

    Priority:
    1. X-Operator-Key fingerprint (set by auth/dependencies.py) -> operator:<fp>
    2. Authenticated user (JWT) -> tenant:xxx:user:yyy
    3. API Key -> apikey:prefix
    4. IP address -> ip:xxx.xxx.xxx.xxx
    """
    # CAB-2146: operator-key gets its own bucket per key fingerprint so distinct
    # operators don't share a single rate-limit bucket (previous keying collapsed
    # every operator onto `tenant:default:user:stoa-operator`).
    operator_fingerprint = getattr(request.state, "operator_fingerprint", None)
    if operator_fingerprint:
        return f"operator:{operator_fingerprint}"

    # CAB-2146: `request.state.user` is stored as a dict in auth/dependencies.py,
    # not an object. The previous `getattr(user, "sub", "unknown")` always hit
    # the default because dicts don't expose keys as attributes — all JWT users
    # collapsed to `tenant:default:user:unknown`.
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        tenant_id = user.get("tenant_id") or user.get("azp") or "default"
        user_id = user.get("sub") or "unknown"
        return f"tenant:{tenant_id}:user:{user_id}"

    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key[:16]}"

    return f"ip:{get_remote_address(request)}"


def get_strict_rate_limit_key(request: Request) -> str:
    """
    Stricter rate limit key for sensitive operations (tool invocations).
    Always includes both tenant and user for better isolation.
    """
    base_key = get_rate_limit_key(request)
    # Add endpoint path for more granular limiting
    path = request.url.path
    return f"{base_key}:path:{path}"


# =============================================================================
# Limiter Configuration
# =============================================================================

# Default limits by authentication type
DEFAULT_LIMITS = {
    "authenticated": "100/minute",  # JWT users
    "api_key": "200/minute",  # Service accounts with API keys
    "anonymous": "30/minute",  # Anonymous/IP-based
    "tool_invoke": "60/minute",  # Tool invocations (stricter)
    "subscription": "30/minute",  # Subscription operations
}

# Create the limiter instance
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["100/minute"],
    storage_uri="memory://",  # MVP: in-memory, Future: redis://
    strategy="fixed-window",
)


# =============================================================================
# Rate Limit Exception Handler
# =============================================================================


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for 429 Too Many Requests responses.
    Returns a JSON response with retry information.
    """
    # Extract rate limit info from exception
    limit = getattr(exc, "limit", "unknown")

    # Log the rate limit event
    logger.warning(
        "rate_limit_exceeded",
        key=get_rate_limit_key(request),
        path=request.url.path,
        method=request.method,
        limit=str(limit),
    )

    # Calculate retry-after (default 60 seconds)
    retry_after = 60

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded: {limit}",
            "detail": "Too many requests. Please slow down and retry later.",
            "retry_after_seconds": retry_after,
            "documentation": "https://docs.gostoa.dev/rate-limits",
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
        },
    )


# =============================================================================
# Convenience Decorators
# =============================================================================


def limit_authenticated(limit: str = DEFAULT_LIMITS["authenticated"]):
    """Rate limit for authenticated endpoints."""
    return limiter.limit(limit, key_func=get_rate_limit_key)


def limit_tool_invoke(limit: str = DEFAULT_LIMITS["tool_invoke"]):
    """Stricter rate limit for tool invocations."""
    return limiter.limit(limit, key_func=get_strict_rate_limit_key)


def limit_subscription(limit: str = DEFAULT_LIMITS["subscription"]):
    """Rate limit for subscription operations."""
    return limiter.limit(limit, key_func=get_rate_limit_key)


def limit_anonymous(limit: str = DEFAULT_LIMITS["anonymous"]):
    """Rate limit for anonymous/public endpoints."""
    return limiter.limit(limit)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "DEFAULT_LIMITS",
    "get_rate_limit_key",
    "get_strict_rate_limit_key",
    "limit_anonymous",
    "limit_authenticated",
    "limit_subscription",
    "limit_tool_invoke",
    "limiter",
    "rate_limit_exceeded_handler",
]
