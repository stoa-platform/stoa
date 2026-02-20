"""
Rate Limiting Middleware for MCP Gateway (CAB-DDoS)

Application-level rate limiting using slowapi.
Works alongside nginx ingress rate limiting for defense-in-depth.

Rate limit tiers:
- General API: 60 req/min per IP
- OAuth proxy endpoints: 10 req/min per IP (strict - amplification risk)
- Tool invocations: 30 req/min per IP
- Public info endpoints: 120 req/min per IP (lenient)
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract real client IP, considering X-Forwarded-For from ingress."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the chain is the real client
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


# Create the limiter instance
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["60/minute"],
    storage_uri="memory://",
    strategy="fixed-window",
)

# Rate limit constants for use in decorators
OAUTH_LIMIT = "10/minute"      # Strict: OAuth proxy endpoints (amplification risk)
TOOL_INVOKE_LIMIT = "30/minute" # Tool invocations
REGISTER_LIMIT = "5/minute"     # DCR registration (very strict)
PUBLIC_LIMIT = "120/minute"     # Public info/health endpoints


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for 429 Too Many Requests."""
    limit = getattr(exc, "limit", "unknown")

    logger.warning(
        "rate_limit_exceeded",
        client_ip=get_client_ip(request),
        path=request.url.path,
        method=request.method,
        limit=str(limit),
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded: {limit}",
            "detail": "Too many requests. Please slow down and retry later.",
            "retry_after_seconds": 60,
        },
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": str(limit),
        },
    )


__all__ = [
    "limiter",
    "get_client_ip",
    "rate_limit_exceeded_handler",
    "OAUTH_LIMIT",
    "TOOL_INVOKE_LIMIT",
    "REGISTER_LIMIT",
    "PUBLIC_LIMIT",
]
