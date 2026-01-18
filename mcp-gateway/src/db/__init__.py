"""CAB-660: Database models and repositories for Tool Handlers."""

from .models import (
    Base,
    Tenant,
    User,
    API,
    APIEndpoint,
    Subscription,
    AuditLog,
    UACContract,
)
from .repositories import (
    # DTOs
    TenantDTO,
    APIDTO,
    APIEndpointDTO,
    SubscriptionDTO,
    AuditLogDTO,
    UACContractDTO,
    # Repositories
    BaseRepository,
    TenantRepository,
    APIRepository,
    SubscriptionRepository,
    AuditLogRepository,
    UACContractRepository,
)

__all__ = [
    # Models
    "Base",
    "Tenant",
    "User",
    "API",
    "APIEndpoint",
    "Subscription",
    "AuditLog",
    "UACContract",
    # DTOs
    "TenantDTO",
    "APIDTO",
    "APIEndpointDTO",
    "SubscriptionDTO",
    "AuditLogDTO",
    "UACContractDTO",
    # Repositories
    "BaseRepository",
    "TenantRepository",
    "APIRepository",
    "SubscriptionRepository",
    "AuditLogRepository",
    "UACContractRepository",
]
