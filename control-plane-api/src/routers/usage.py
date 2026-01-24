"""
Usage API Router - CAB-280 / CAB-840
Endpoints pour le Dashboard Usage Consumer (Portal)

Routes:
- GET /v1/usage/me - Résumé de mon usage
- GET /v1/usage/me/calls - Mes derniers appels
- GET /v1/usage/me/subscriptions - Mes subscriptions actives

Data Sources (CAB-840):
- Prometheus: Metrics (request counts, latencies, success rates)
- Loki: Logs (call history, activity feed)
- PostgreSQL: Subscription data, tool counts
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException

from ..auth import get_current_user, User
from ..database import get_db
from ..services.metrics_service import metrics_service
from ..schemas.usage import (
    UsageSummary,
    UsageCallsResponse,
    ActiveSubscription,
    CallStatus,
    DashboardStats,
    DashboardActivityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/usage", tags=["Usage"])

# Also create dashboard router
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["Dashboard"])


# ============================================================
# GET /v1/usage/me - Résumé complet de mon usage
# ============================================================

@router.get("/me", response_model=UsageSummary)
async def get_my_usage_summary(
    current_user: User = Depends(get_current_user)
) -> UsageSummary:
    """
    Retourne le résumé d'usage pour l'utilisateur connecté.

    Inclut:
    - Stats aujourd'hui / cette semaine / ce mois
    - Top 5 des tools les plus utilisés
    - Evolution des appels sur 7 jours

    Data Sources (CAB-840):
    - Prometheus for metrics
    - Falls back to empty data if Prometheus unavailable
    """
    user_id = current_user.id
    tenant_id = current_user.tenant_id or "default"

    logger.info(f"Fetching usage summary for user={user_id} tenant={tenant_id}")

    try:
        return await metrics_service.get_usage_summary(user_id, tenant_id)
    except Exception as e:
        logger.error(f"Failed to fetch usage summary: {e}")
        raise HTTPException(
            status_code=503,
            detail="Usage metrics temporarily unavailable"
        )


# ============================================================
# GET /v1/usage/me/calls - Mes derniers appels
# ============================================================

@router.get("/me/calls", response_model=UsageCallsResponse)
async def get_my_calls(
    limit: int = Query(default=20, ge=1, le=100, description="Number of calls to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    status: Optional[CallStatus] = Query(default=None, description="Filter by call status"),
    tool_id: Optional[str] = Query(default=None, description="Filter by tool ID"),
    from_date: Optional[datetime] = Query(default=None, description="Start date filter"),
    to_date: Optional[datetime] = Query(default=None, description="End date filter"),
    current_user: User = Depends(get_current_user)
) -> UsageCallsResponse:
    """
    Retourne la liste paginée des derniers appels MCP de l'utilisateur.

    Filtres disponibles:
    - status: success, error, timeout
    - tool_id: filtrer par tool
    - from_date / to_date: période

    Data Sources (CAB-840):
    - Loki for call logs
    - Falls back to empty list if Loki unavailable
    """
    user_id = current_user.id
    tenant_id = current_user.tenant_id or "default"

    logger.info(f"Fetching calls for user={user_id} limit={limit} offset={offset} status={status}")

    try:
        return await metrics_service.get_user_calls(
            user_id=user_id,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            tool_id=tool_id,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        logger.error(f"Failed to fetch calls: {e}")
        raise HTTPException(
            status_code=503,
            detail="Call history temporarily unavailable"
        )


# ============================================================
# GET /v1/usage/me/subscriptions - Mes subscriptions actives
# ============================================================

@router.get("/me/subscriptions", response_model=list[ActiveSubscription])
async def get_my_active_subscriptions(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
) -> list[ActiveSubscription]:
    """
    Retourne la liste des subscriptions actives de l'utilisateur.

    Data Sources (CAB-840):
    - PostgreSQL for subscription data
    - Prometheus for usage counts (with DB fallback)
    """
    user_id = current_user.id

    logger.info(f"Fetching active subscriptions for user={user_id}")

    try:
        return await metrics_service.get_active_subscriptions(user_id, db)
    except Exception as e:
        logger.error(f"Failed to fetch subscriptions: {e}")
        raise HTTPException(
            status_code=503,
            detail="Subscription data temporarily unavailable"
        )


# ============================================================
# Dashboard Endpoints (CAB-299)
# ============================================================

@dashboard_router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
) -> DashboardStats:
    """
    Retourne les statistiques agrégées pour la home page du Portal.

    Inclut:
    - Nombre de tools disponibles
    - Nombre de subscriptions actives
    - Nombre d'appels API cette semaine
    - Tendances (% change)

    Data Sources (CAB-840):
    - PostgreSQL for tool/subscription counts
    - Prometheus for API call metrics and trends
    """
    user_id = current_user.id
    tenant_id = current_user.tenant_id or "default"

    logger.info(f"Fetching dashboard stats for user={user_id} tenant={tenant_id}")

    try:
        return await metrics_service.get_dashboard_stats(user_id, tenant_id, db)
    except Exception as e:
        logger.error(f"Failed to fetch dashboard stats: {e}")
        raise HTTPException(
            status_code=503,
            detail="Dashboard stats temporarily unavailable"
        )


@dashboard_router.get("/activity", response_model=DashboardActivityResponse)
async def get_dashboard_activity(
    limit: int = Query(default=5, ge=1, le=20, description="Number of activities to return"),
    current_user: User = Depends(get_current_user)
) -> DashboardActivityResponse:
    """
    Retourne l'activité récente pour la home page du Portal.

    Data Sources (CAB-840):
    - Loki for activity logs
    - Falls back to empty list if Loki unavailable
    """
    user_id = current_user.id
    tenant_id = current_user.tenant_id or "default"

    logger.info(f"Fetching dashboard activity for user={user_id} limit={limit}")

    try:
        activity = await metrics_service.get_dashboard_activity(user_id, tenant_id, limit)
        return DashboardActivityResponse(activity=activity)
    except Exception as e:
        logger.error(f"Failed to fetch dashboard activity: {e}")
        raise HTTPException(
            status_code=503,
            detail="Activity feed temporarily unavailable"
        )
