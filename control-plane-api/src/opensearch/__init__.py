"""
STOA Platform - OpenSearch Integration
======================================

Provides OpenSearch-based search, audit logging, and analytics.

Components:
- audit_middleware: FastAPI middleware for audit trail
- search_router: Search API endpoints
- opensearch_integration: Client and dependency injection
"""

from .audit_middleware import (
    AuditEvent,
    AuditLogger,
    AuditMiddleware,
    EventCategory,
    EventSeverity,
    log_audit_event,
)
from .opensearch_integration import (
    OpenSearchService,
    OpenSearchSettings,
    get_audit_logger,
    get_opensearch_client,
    get_settings,
    opensearch_lifespan,
    setup_opensearch,
)
from .search_router import router as search_router

__all__ = [
    # Audit
    "AuditEvent",
    "AuditLogger",
    "AuditMiddleware",
    "EventCategory",
    "EventSeverity",
    "log_audit_event",
    # Integration
    "OpenSearchService",
    "OpenSearchSettings",
    "get_audit_logger",
    "get_opensearch_client",
    "get_settings",
    "opensearch_lifespan",
    "setup_opensearch",
    # Search
    "search_router",
]
