"""
src.lifecycle -- Tenant Lifecycle Management
CAB-409: Auto-Cleanup & Notifications for demo.gostoa.dev

Module structure:
    models.py         -- Enums, Pydantic schemas, SQLAlchemy mixin, Notification ORM
    service.py        -- State machine & business logic
    cleanup.py        -- Infrastructure cleanup (K8s, Keycloak, Vault)
    notifications.py  -- Email notification service & templates
    metrics.py        -- Prometheus metrics
    routes.py         -- FastAPI endpoints
    cli.py            -- CronJob entry point
"""
from .models import (
    TenantLifecycleState,
    NotificationType,
    TenantStatusResponse,
    ExtendTrialRequest,
    ExtendTrialResponse,
    UpgradeTenantRequest,
    UpgradeTenantResponse,
    LifecycleTransitionEvent,
    LifecycleCronSummary,
    TenantLifecycleMixin,
    TenantLifecycleNotification,
    TRIAL_DURATION_DAYS,
    WARNING_THRESHOLD_DAYS,
    GRACE_PERIOD_DAYS,
    CLEANUP_AFTER_DAYS,
    MAX_EXTENSIONS,
    EXTENSION_DAYS,
)
from .service import TenantLifecycleService, LifecycleError, TenantNotFoundError
from .cleanup import CleanupService
from .notifications import NotificationService
from .metrics import lifecycle_metrics
from .routes import router as lifecycle_router, admin_router as lifecycle_admin_router

__all__ = [
    "TenantLifecycleState",
    "NotificationType",
    "TenantStatusResponse",
    "ExtendTrialRequest",
    "ExtendTrialResponse",
    "UpgradeTenantRequest",
    "UpgradeTenantResponse",
    "LifecycleTransitionEvent",
    "LifecycleCronSummary",
    "TenantLifecycleMixin",
    "TenantLifecycleNotification",
    "TenantLifecycleService",
    "CleanupService",
    "NotificationService",
    "lifecycle_metrics",
    "lifecycle_router",
    "lifecycle_admin_router",
    "LifecycleError",
    "TenantNotFoundError",
    "TRIAL_DURATION_DAYS",
    "WARNING_THRESHOLD_DAYS",
    "GRACE_PERIOD_DAYS",
    "CLEANUP_AFTER_DAYS",
    "MAX_EXTENSIONS",
    "EXTENSION_DAYS",
]
