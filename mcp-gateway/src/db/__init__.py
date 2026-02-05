"""CAB-660: Database models for MCP Gateway.

ADR-001 Compliance: Repositories removed - MCP Gateway uses CoreAPIClient
to access data via Control-Plane-API instead of direct database access.

Note: db/models.py is still used for MCP Subscription management
(tool subscriptions with API keys) and error snapshots.
"""

from .models import (
    API,
    APIEndpoint,
    AuditLog,
    Base,
    Subscription,
    Tenant,
    UACContract,
    User,
)

__all__ = [
    # Models (still used for MCP subscriptions and migrations)
    "Base",
    "Tenant",
    "User",
    "API",
    "APIEndpoint",
    "Subscription",
    "AuditLog",
    "UACContract",
]
