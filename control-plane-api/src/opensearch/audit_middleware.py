"""
STOA Platform - Audit Trail Middleware
======================================

FastAPI middleware to capture and log audit events to OpenSearch.

Features:
- Automatic capture of API calls
- Actor identification from JWT
- Resource extraction from request
- Async non-blocking logging
- Configurable event filtering
- Structured audit events

Usage:
    from audit_middleware import AuditMiddleware, AuditLogger

    app = FastAPI()
    audit_logger = AuditLogger(opensearch_client)
    app.add_middleware(AuditMiddleware, audit_logger=audit_logger)
"""

import contextlib
import hashlib
import ipaddress
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import Request, Response
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("stoa.audit")

# Context variable for correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

# Data minimisation of the actor's network identifiers (applied before either
# audit store is written): the source address is reduced to its network and the
# user agent is only kept when the call did not succeed.
IPV4_TRUNCATION_PREFIX = 24
IPV6_TRUNCATION_PREFIX = 48
# Longest user agent kept on a failed call: the width of audit_events.user_agent
# (String(512)). The cut counts code points, like the PostgreSQL column: it is
# safe for UTF-8 (a multi-byte character is kept whole or dropped whole) but it
# may separate a grapheme (a combining mark, an emoji ZWJ sequence).
USER_AGENT_MAX_LENGTH = 512


# IPv6 prefixes that embed an IPv4 address (RFC 4291 s2.5.5, RFC 6052, RFC 8215,
# RFC 4380 and RFC 3056, the last two via ``ipaddress``). The embedded IPv4 address is extracted and minimised with
# the IPv4 policy, so that none of these forms can carry a full IPv4 address past
# the /48 truncation (6to4 and the /48 NAT64 layout keep it in the top 48 bits).
_IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")  # deprecated ::a.b.c.d
_NAT64_WELL_KNOWN = ipaddress.IPv6Network("64:ff9b::/96")  # RFC 6052 s2.1
_NAT64_LOCAL_USE = ipaddress.IPv6Network("64:ff9b:1::/48")  # RFC 8215
_LOW_32_BITS = (1 << 32) - 1


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Return the IPv4 address embedded in ``address``, or ``None``.

    Forms handled: IPv4-mapped (``::ffff:a.b.c.d``), IPv4-compatible
    (``::a.b.c.d``, deprecated; ``::`` and ``::1`` are not IPv4-compatible
    addresses and are left to the IPv6 rule), NAT64 well-known prefix
    (``64:ff9b::/96``), NAT64 local-use prefix (``64:ff9b:1::/48``, only in its
    /96 layout: the other RFC 6052 layouts cannot be told apart without the
    operator's prefix length, and the /48 truncation then drops every bit of the
    IPv4 address anyway), Teredo (``2001::/32``: the client address, XOR-decoded;
    the Teredo server address is not the caller and is dropped) and 6to4
    (``2002::/16``).
    """
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address.teredo is not None:
        _server, client = address.teredo
        return client
    if address in _NAT64_WELL_KNOWN:
        return ipaddress.IPv4Address(int(address) & _LOW_32_BITS)
    if address in _NAT64_LOCAL_USE:
        middle_bits = (int(address) >> 32) & ((1 << 48) - 1)  # bits 48-95
        if middle_bits == 0:
            return ipaddress.IPv4Address(int(address) & _LOW_32_BITS)
        return None
    if address in _IPV4_COMPATIBLE and int(address) > 1:
        return ipaddress.IPv4Address(int(address) & _LOW_32_BITS)
    return None


def truncate_ip(host: str | None) -> str | None:
    """Return the network address of ``host`` (IPv4 /24, IPv6 /48).

    ``None`` and ``""`` are returned unchanged. A value that is not a string, or
    that does not parse as an IP address (e.g. a unix socket path or a test
    client name), is refused: the function returns ``None`` so that an
    unminimised value is never written and the audit event is never lost. An
    IPv6 address that embeds an IPv4 address (see :func:`_embedded_ipv4`) is
    truncated as that IPv4 address. A zone index (``%eth0``) is dropped.
    """
    if host is not None and not isinstance(host, str):
        return None
    if not host:
        return host
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            address = embedded
    prefix = IPV4_TRUNCATION_PREFIX if address.version == 4 else IPV6_TRUNCATION_PREFIX
    network = ipaddress.ip_network((address, prefix), strict=False)
    return str(network.network_address)


def minimise_actor(actor: dict, outcome: str) -> dict:
    """Apply the data-minimisation rules to an extracted actor, in place.

    The source address is truncated with :func:`truncate_ip`; the user agent is
    dropped when ``outcome`` is ``"success"`` and kept otherwise (failure,
    denied, error), where it is useful to investigate the call, cut to
    :data:`USER_AGENT_MAX_LENGTH` code points. A kept user agent that is not a
    string is refused (``None``), like a source address that is not a string in
    :func:`truncate_ip`; ``None`` and ``""`` are returned unchanged.
    """
    actor["ip_address"] = truncate_ip(actor.get("ip_address"))
    if outcome == "success":
        actor["user_agent"] = None
    else:
        user_agent = actor.get("user_agent")
        if user_agent is not None and not isinstance(user_agent, str):
            actor["user_agent"] = None
        elif isinstance(user_agent, str) and len(user_agent) > USER_AGENT_MAX_LENGTH:
            actor["user_agent"] = user_agent[:USER_AGENT_MAX_LENGTH]
    return actor


class EventCategory(StrEnum):
    """Audit event categories."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    SECURITY = "security"


class EventSeverity(StrEnum):
    """Audit event severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEvent(BaseModel):
    """Audit event model for OpenSearch."""

    timestamp: datetime = Field(alias="@timestamp")
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    event_category: EventCategory
    severity: EventSeverity = EventSeverity.INFO

    actor: dict = Field(default_factory=dict)
    tenant_id: str | None = None
    resource: dict = Field(default_factory=dict)
    action: str
    outcome: str = "success"

    details: dict = Field(default_factory=dict)
    changes: dict = Field(default_factory=dict)

    request: dict = Field(default_factory=dict)
    response: dict = Field(default_factory=dict)

    correlation_id: str | None = None
    session_id: str | None = None

    source: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True
        use_enum_values = True


class AuditLogger:
    """Async audit logger to OpenSearch."""

    def __init__(
        self,
        client: AsyncOpenSearch,
        index_alias: str = "audit",
        buffer_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.client = client
        self.index_alias = index_alias
        self.buffer: list[dict] = []
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self._last_flush = time.time()

    async def log(self, event: AuditEvent) -> None:
        """Log an audit event."""
        doc = event.model_dump(by_alias=True, exclude_none=True)
        doc["@timestamp"] = doc["@timestamp"].isoformat()

        self.buffer.append(
            {
                "_index": self.index_alias,
                "_source": doc,
            }
        )

        # Flush if buffer is full or interval exceeded
        if len(self.buffer) >= self.buffer_size or (time.time() - self._last_flush) > self.flush_interval:
            await self.flush()

    async def flush(self) -> None:
        """Flush buffered events to OpenSearch."""
        if not self.buffer:
            return

        try:
            from opensearchpy.helpers import async_bulk

            success, errors = await async_bulk(
                self.client,
                self.buffer,
                raise_on_error=False,
            )

            if errors:
                logger.error(f"Failed to index {len(errors)} audit events")

            logger.debug(f"Flushed {success} audit events to OpenSearch")

        except Exception as e:
            logger.error(f"Error flushing audit events: {e}")
        finally:
            self.buffer.clear()
            self._last_flush = time.time()

    async def log_event(
        self,
        event_type: str,
        category: EventCategory,
        action: str,
        actor: dict,
        resource: dict | None = None,
        tenant_id: str | None = None,
        outcome: str = "success",
        severity: EventSeverity = EventSeverity.INFO,
        details: dict | None = None,
        changes: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Log a custom audit event."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            event_category=category,
            severity=severity,
            actor=actor,
            tenant_id=tenant_id,
            resource=resource or {},
            action=action,
            outcome=outcome,
            details=details or {},
            changes=changes or {},
            correlation_id=correlation_id_ctx.get(),
            source={
                "service": "stoa-control-plane",
                "version": "0.1.0",
                "environment": "production",
            },
            tags=tags or [],
        )
        await self.log(event)


def parse_server_timing(header: str) -> dict[str, float]:
    """Parse a Server-Timing header into a dict of stage → duration_ms.

    Format: "stage;dur=12.34, stage2;dur=5.67"
    Returns: {"stage": 12.34, "stage2": 5.67}
    """
    timings: dict[str, float] = {}
    for entry in header.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(";")
        name = parts[0].strip()
        for param in parts[1:]:
            param = param.strip()
            if param.startswith("dur="):
                with contextlib.suppress(ValueError):
                    timings[name] = float(param[4:])
    return timings


class AuditMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic audit logging."""

    # Paths to skip auditing
    SKIP_PATHS = {
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/favicon.ico",
    }

    # Methods that indicate data modification
    MODIFICATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    # Path patterns that indicate sensitive operations
    SENSITIVE_PATTERNS = {
        "/api-keys": "api_key",
        "/subscriptions": "subscription",
        "/tenants": "tenant",
        "/users": "user",
        "/roles": "role",
        "/webhooks": "webhook",
        "/secrets": "secret",
    }

    def __init__(
        self,
        app,
        audit_logger: AuditLogger | None = None,
        skip_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self._audit_logger = audit_logger
        self.skip_paths = skip_paths or self.SKIP_PATHS

    @property
    def audit_logger(self) -> AuditLogger | None:
        """Lazy lookup: use provided logger or get from OpenSearchService singleton."""
        if self._audit_logger:
            return self._audit_logger
        try:
            from .opensearch_integration import OpenSearchService

            service = OpenSearchService.get_instance()
            return service.audit_logger
        except Exception:
            return None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and log audit event."""

        # Skip if audit logger not yet initialized (OpenSearch not connected)
        if not self.audit_logger:
            return await call_next(request)

        # Skip non-auditable paths
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # Generate/extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        correlation_id_ctx.set(correlation_id)

        # Start timing
        start_time = time.time()

        # Process request
        response = None
        try:
            response = await call_next(request)
            outcome = "success" if response.status_code < 400 else "failure"
            severity = self._get_severity(response.status_code)
        except Exception:
            outcome = "error"
            severity = EventSeverity.ERROR
            raise
        finally:
            # Extract actor AFTER call_next so that endpoint-level
            # Depends(get_current_user) has populated request.state.user
            actor = minimise_actor(await self._extract_actor(request), outcome)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Determine event type and category
            event_type, category = self._classify_request(request)

            # Build audit event
            event = AuditEvent(
                timestamp=datetime.now(UTC),
                event_type=event_type,
                event_category=category,
                severity=severity,
                actor=actor,
                tenant_id=actor.get("tenant_id") or "platform",
                resource=self._extract_resource(request),
                action=f"{request.method} {request.url.path}",
                outcome=outcome,
                request={
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": dict(request.query_params),
                    "body_hash": await self._hash_body(request),
                },
                response=self._build_response_dict(response, latency_ms),
                correlation_id=correlation_id,
                session_id=request.headers.get("X-Session-ID"),
                source={
                    "service": "stoa-control-plane",
                    "version": "0.1.0",
                    "environment": "production",
                },
                tags=self._get_tags(request),
            )

            # Log to OpenSearch (non-blocking)
            try:
                await self.audit_logger.log(event)
            except Exception as e:
                logger.error(f"Failed to log audit event to OpenSearch: {e}")

            # Dual-write mutating requests to PostgreSQL (CAB-1475)
            if request.method in self.MODIFICATION_METHODS:
                try:
                    resource = self._extract_resource(request)
                    await self._write_pg_audit(
                        tenant_id=actor.get("tenant_id") or "platform",
                        actor_id=actor.get("id"),
                        actor_email=actor.get("email"),
                        actor_type=actor.get("type", "user"),
                        action=event_type,
                        method=request.method,
                        path=request.url.path,
                        resource_type=resource.get("type", "unknown"),
                        resource_id=resource.get("id"),
                        outcome=outcome,
                        status_code=response.status_code,
                        client_ip=actor.get("ip_address"),
                        user_agent=actor.get("user_agent"),
                        correlation_id=correlation_id,
                        duration_ms=round(latency_ms),
                    )
                except Exception as e:
                    logger.warning(f"Failed to dual-write audit event to PG: {e}")

        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id

        return response

    async def _write_pg_audit(
        self,
        *,
        tenant_id: str,
        actor_id: str | None,
        actor_email: str | None,
        actor_type: str,
        action: str,
        method: str,
        path: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        status_code: int | None,
        client_ip: str | None,
        user_agent: str | None,
        correlation_id: str | None,
        duration_ms: int | None,
    ) -> None:
        """Write audit event to PostgreSQL (separate session, non-blocking)."""
        from ..database import get_async_session_factory
        from ..services.audit_service import AuditService

        session_factory = get_async_session_factory()
        if not session_factory:
            return

        async with session_factory() as session:
            service = AuditService(session)
            await service.record_event(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_email=actor_email,
                actor_type=actor_type,
                action=action,
                method=method,
                path=path,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                status_code=status_code,
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
            )
            await session.commit()

    async def _extract_actor(self, request: Request) -> dict:
        """Extract actor information from request."""
        actor = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
        }

        # Extract from JWT if available
        if hasattr(request.state, "user"):
            user = request.state.user
            actor.update(
                {
                    "id": user.get("sub"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                    # "operator" for X-Operator-Key callers (CAB-2079 P3-03), "user" otherwise
                    "type": user.get("type", "user"),
                    "tenant_id": user.get("tenant_id"),
                }
            )
            if user.get("operator_fingerprint"):
                actor["operator_fingerprint"] = user["operator_fingerprint"]
        elif hasattr(request.state, "api_key"):
            api_key = request.state.api_key
            actor.update(
                {
                    "id": api_key.get("id"),
                    "name": api_key.get("name"),
                    "type": "api_key",
                    "tenant_id": api_key.get("tenant_id"),
                }
            )
        elif request.headers.get("X-Gateway-Key"):
            actor.update(
                {
                    "id": "stoa-gateway",
                    "name": "stoa-gateway",
                    "type": "service",
                }
            )
        elif request.url.path.startswith("/v1/internal/"):
            actor.update(
                {
                    "id": "internal-service",
                    "name": "internal-service",
                    "type": "service",
                }
            )
        else:
            actor["type"] = "anonymous"

        return actor

    def _extract_resource(self, request: Request) -> dict:
        """Extract resource information from request path."""
        path_parts = request.url.path.strip("/").split("/")

        resource = {
            "type": "unknown",
            "id": None,
            "name": None,
        }

        # Try to identify resource type and ID
        for pattern, resource_type in self.SENSITIVE_PATTERNS.items():
            if pattern.strip("/") in path_parts:
                resource["type"] = resource_type
                # Try to get resource ID (usually after the pattern)
                try:
                    idx = path_parts.index(pattern.strip("/"))
                    if idx + 1 < len(path_parts):
                        resource["id"] = path_parts[idx + 1]
                except (ValueError, IndexError):
                    pass
                break

        return resource

    def _classify_request(self, request: Request) -> tuple[str, EventCategory]:
        """Classify request into event type and category."""
        method = request.method
        path = request.url.path

        # Authentication endpoints
        if "/auth" in path or "/login" in path or "/token" in path:
            return "authentication", EventCategory.AUTHENTICATION

        # Data modification
        if method in self.MODIFICATION_METHODS:
            for pattern in self.SENSITIVE_PATTERNS:
                if pattern in path:
                    if method == "DELETE":
                        return f"{self.SENSITIVE_PATTERNS[pattern]}.deleted", EventCategory.DATA_MODIFICATION
                    elif method == "POST":
                        return f"{self.SENSITIVE_PATTERNS[pattern]}.created", EventCategory.DATA_MODIFICATION
                    else:
                        return f"{self.SENSITIVE_PATTERNS[pattern]}.updated", EventCategory.DATA_MODIFICATION
            return "data.modified", EventCategory.DATA_MODIFICATION

        # Data access
        return "data.accessed", EventCategory.DATA_ACCESS

    def _get_severity(self, status_code: int) -> EventSeverity:
        """Determine severity from status code."""
        if status_code >= 500:
            return EventSeverity.ERROR
        elif status_code >= 400:
            return EventSeverity.WARNING
        return EventSeverity.INFO

    def _get_tags(self, request: Request) -> list[str]:
        """Generate tags for the request."""
        tags = []

        # Add method tag
        tags.append(f"method:{request.method.lower()}")

        # Add version tag if present
        if "/v1/" in request.url.path:
            tags.append("api:v1")
        elif "/v2/" in request.url.path:
            tags.append("api:v2")

        # Add sensitive tag if applicable
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in request.url.path:
                tags.append("sensitive")
                break

        return tags

    @staticmethod
    def _build_response_dict(response: Response | None, latency_ms: float) -> dict:
        """Build response dict for audit event, including gateway span timings."""
        resp: dict = {
            "status_code": response.status_code if response else 500,
            "latency_ms": round(latency_ms, 2),
        }
        # Capture Server-Timing header from upstream (gateway) responses (CAB-1790)
        if response:
            server_timing = response.headers.get("server-timing")
            if server_timing:
                resp["gateway_timings"] = parse_server_timing(server_timing)
        return resp

    async def _hash_body(self, request: Request) -> str | None:
        """Create a hash of the request body for audit (no sensitive data)."""
        try:
            body = await request.body()
            if body:
                return hashlib.sha256(body).hexdigest()[:16]
        except Exception:
            pass
        return None


# Convenience functions for manual audit logging
async def log_audit_event(
    audit_logger: AuditLogger,
    event_type: str,
    action: str,
    actor_id: str,
    actor_email: str | None = None,
    tenant_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
    details: dict | None = None,
    changes: dict | None = None,
) -> None:
    """Log a manual audit event (for business logic events)."""
    await audit_logger.log_event(
        event_type=event_type,
        category=EventCategory.DATA_MODIFICATION,
        action=action,
        actor={
            "id": actor_id,
            "email": actor_email,
            "type": "user",
        },
        tenant_id=tenant_id,
        resource=(
            {
                "type": resource_type,
                "id": resource_id,
            }
            if resource_type
            else None
        ),
        outcome=outcome,
        details=details,
        changes=changes,
    )


# Example usage in FastAPI route
"""
from fastapi import Depends
from audit_middleware import log_audit_event, AuditLogger

@router.post("/subscriptions")
async def create_subscription(
    data: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    # Create subscription...
    subscription = await subscription_service.create(data)

    # Log audit event
    await log_audit_event(
        audit_logger=audit_logger,
        event_type="subscription.created",
        action="create_subscription",
        actor_id=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource_type="subscription",
        resource_id=subscription.id,
        details={"plan": data.plan, "tool_id": data.tool_id},
    )

    return subscription
"""
