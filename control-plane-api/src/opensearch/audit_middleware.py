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

import hashlib
import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from fastapi import Request, Response
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("stoa.audit")

# Context variable for correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


class EventCategory(str, Enum):
    """Audit event categories."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    SECURITY = "security"


class EventSeverity(str, Enum):
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
    tenant_id: Optional[str] = None
    resource: dict = Field(default_factory=dict)
    action: str
    outcome: str = "success"
    
    details: dict = Field(default_factory=dict)
    changes: dict = Field(default_factory=dict)
    
    request: dict = Field(default_factory=dict)
    response: dict = Field(default_factory=dict)
    
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    
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
        
        self.buffer.append({
            "_index": self.index_alias,
            "_source": doc,
        })
        
        # Flush if buffer is full or interval exceeded
        if len(self.buffer) >= self.buffer_size or \
           (time.time() - self._last_flush) > self.flush_interval:
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
        resource: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        outcome: str = "success",
        severity: EventSeverity = EventSeverity.INFO,
        details: Optional[dict] = None,
        changes: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Log a custom audit event."""
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc),
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
        audit_logger: AuditLogger,
        skip_paths: Optional[set[str]] = None,
    ):
        super().__init__(app)
        self.audit_logger = audit_logger
        self.skip_paths = skip_paths or self.SKIP_PATHS
    
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and log audit event."""
        
        # Skip non-auditable paths
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        # Generate/extract correlation ID
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            str(uuid.uuid4())
        )
        correlation_id_ctx.set(correlation_id)
        
        # Extract actor from JWT
        actor = await self._extract_actor(request)
        
        # Start timing
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            outcome = "success" if response.status_code < 400 else "failure"
            severity = self._get_severity(response.status_code)
        except Exception as e:
            outcome = "error"
            severity = EventSeverity.ERROR
            raise
        finally:
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Determine event type and category
            event_type, category = self._classify_request(request)
            
            # Build audit event
            event = AuditEvent(
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                event_category=category,
                severity=severity,
                actor=actor,
                tenant_id=actor.get("tenant_id"),
                resource=self._extract_resource(request),
                action=f"{request.method} {request.url.path}",
                outcome=outcome,
                request={
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": dict(request.query_params),
                    "body_hash": await self._hash_body(request),
                },
                response={
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                },
                correlation_id=correlation_id,
                session_id=request.headers.get("X-Session-ID"),
                source={
                    "service": "stoa-control-plane",
                    "version": "0.1.0",
                    "environment": "production",
                },
                tags=self._get_tags(request),
            )
            
            # Log asynchronously (non-blocking)
            try:
                await self.audit_logger.log(event)
            except Exception as e:
                logger.error(f"Failed to log audit event: {e}")
        
        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response
    
    async def _extract_actor(self, request: Request) -> dict:
        """Extract actor information from request."""
        actor = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
        }
        
        # Extract from JWT if available
        if hasattr(request.state, "user"):
            user = request.state.user
            actor.update({
                "id": user.get("sub"),
                "email": user.get("email"),
                "name": user.get("name"),
                "type": "user",
                "tenant_id": user.get("tenant_id"),
            })
        elif hasattr(request.state, "api_key"):
            api_key = request.state.api_key
            actor.update({
                "id": api_key.get("id"),
                "name": api_key.get("name"),
                "type": "api_key",
                "tenant_id": api_key.get("tenant_id"),
            })
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
    
    def _classify_request(
        self, request: Request
    ) -> tuple[str, EventCategory]:
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
    
    async def _hash_body(self, request: Request) -> Optional[str]:
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
    actor_email: Optional[str] = None,
    tenant_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    outcome: str = "success",
    details: Optional[dict] = None,
    changes: Optional[dict] = None,
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
        resource={
            "type": resource_type,
            "id": resource_id,
        } if resource_type else None,
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
