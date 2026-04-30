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
    # Integration — CAB-2199 / INFRA-1a S3: OpenSearchSettings was
    # consolidated into Settings.opensearch_audit (a sub-model). Import
    # ``OpenSearchAuditConfig`` from ``src.config`` if you need the type.
    "OpenSearchService",
    "get_audit_logger",
    "get_opensearch_client",
    "get_settings",
    "log_audit_event",
    "opensearch_lifespan",
    # Search
    "search_router",
    "setup_opensearch",
]
