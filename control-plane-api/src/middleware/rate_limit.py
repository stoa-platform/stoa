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

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Rate Limit Key Functions
# =============================================================================

def get_rate_limit_key(request: Request) -> str:
    """
    Generate rate limit key based on authentication context.

    MVP: user_id or API key or IP
    Future (CAB-459): tenant_id + user_id + product_roles

    Priority:
    1. Authenticated user (JWT) -> tenant:xxx:user:yyy
    2. API Key -> apikey:prefix
    3. IP address -> ip:xxx.xxx.xxx.xxx
    """
    # Check for authenticated user from JWT
    user = getattr(request.state, "user", None)
    if user:
        # Prepare for multi-tenant: extract tenant_id when available
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            # Try to extract from JWT claims
            tenant_id = getattr(user, "azp", "default")  # azp = authorized party

        user_id = getattr(user, "sub", "unknown")
        return f"tenant:{tenant_id}:user:{user_id}"

    # Check for API key authentication
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Use first 16 chars as identifier (safe prefix)
        return f"apikey:{api_key[:16]}"

    # Fallback to IP address
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
    "authenticated": "100/minute",    # JWT users
    "api_key": "200/minute",          # Service accounts with API keys
    "anonymous": "30/minute",         # Anonymous/IP-based
    "tool_invoke": "60/minute",       # Tool invocations (stricter)
    "subscription": "30/minute",      # Subscription operations
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
    "limiter",
    "get_rate_limit_key",
    "get_strict_rate_limit_key",
    "rate_limit_exceeded_handler",
    "limit_authenticated",
    "limit_tool_invoke",
    "limit_subscription",
    "limit_anonymous",
    "DEFAULT_LIMITS",
]
