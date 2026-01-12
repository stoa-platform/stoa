"""
Usage API Router - CAB-280
Endpoints pour le Dashboard Usage Consumer (Portal)

Routes:
- GET /v1/usage/me - Résumé de mon usage
- GET /v1/usage/me/calls - Mes derniers appels
- GET /v1/usage/me/subscriptions - Mes subscriptions actives
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user, User
from ..schemas.usage import (
    UsageSummary,
    UsageCallsResponse,
    UsageCall,
    UsagePeriodStats,
    ToolUsageStat,
    DailyCallStat,
    ActiveSubscription,
    CallStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/usage", tags=["Usage"])


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
    """
    user_id = current_user.id
    tenant_id = current_user.tenant_id or "default"

    logger.info(f"Fetching usage summary for user={user_id} tenant={tenant_id}")

    # TODO: Remplacer par vraies queries DB/Prometheus/Loki
    # Pour le MVP, retourner des données simulées

    return UsageSummary(
        tenant_id=tenant_id,
        user_id=user_id,
        today=UsagePeriodStats(
            period="today",
            total_calls=127,
            success_count=120,
            error_count=7,
            success_rate=94.5,
            avg_latency_ms=180
        ),
        this_week=UsagePeriodStats(
            period="week",
            total_calls=842,
            success_count=810,
            error_count=32,
            success_rate=96.2,
            avg_latency_ms=165
        ),
        this_month=UsagePeriodStats(
            period="month",
            total_calls=3254,
            success_count=3180,
            error_count=74,
            success_rate=97.7,
            avg_latency_ms=158
        ),
        top_tools=[
            ToolUsageStat(tool_id="crm-search", tool_name="CRM Customer Search", call_count=1250, success_rate=98.5, avg_latency_ms=120),
            ToolUsageStat(tool_id="billing-invoice", tool_name="Billing Invoice Generator", call_count=890, success_rate=97.2, avg_latency_ms=200),
            ToolUsageStat(tool_id="inventory-check", tool_name="Inventory Availability", call_count=654, success_rate=99.1, avg_latency_ms=85),
            ToolUsageStat(tool_id="notification-send", tool_name="Send Notification", call_count=412, success_rate=95.8, avg_latency_ms=320),
            ToolUsageStat(tool_id="analytics-report", tool_name="Analytics Report", call_count=48, success_rate=100.0, avg_latency_ms=1200),
        ],
        daily_calls=[
            DailyCallStat(date="2026-01-06", calls=120),
            DailyCallStat(date="2026-01-07", calls=135),
            DailyCallStat(date="2026-01-08", calls=98),
            DailyCallStat(date="2026-01-09", calls=156),
            DailyCallStat(date="2026-01-10", calls=142),
            DailyCallStat(date="2026-01-11", calls=118),
            DailyCallStat(date="2026-01-12", calls=73),
        ]
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
    """
    user_id = current_user.id

    logger.info(f"Fetching calls for user={user_id} limit={limit} offset={offset} status={status}")

    # TODO: Remplacer par vraies queries DB/Loki
    # Pour le MVP, retourner des données simulées

    now = datetime.utcnow()

    mock_calls = [
        UsageCall(
            id=f"call-{i:04d}",
            timestamp=now - timedelta(minutes=i * 5),
            tool_id="crm-search" if i % 3 == 0 else "billing-invoice" if i % 3 == 1 else "inventory-check",
            tool_name="CRM Customer Search" if i % 3 == 0 else "Billing Invoice" if i % 3 == 1 else "Inventory Check",
            status=CallStatus.SUCCESS if i % 7 != 0 else CallStatus.ERROR,
            latency_ms=100 + (i * 10) % 300,
            error_message="Connection timeout" if i % 7 == 0 else None
        )
        for i in range(limit)
    ]

    # Appliquer les filtres si spécifiés
    if status:
        mock_calls = [c for c in mock_calls if c.status == status]
    if tool_id:
        mock_calls = [c for c in mock_calls if c.tool_id == tool_id]

    return UsageCallsResponse(
        calls=mock_calls,
        total=247,
        limit=limit,
        offset=offset
    )


# ============================================================
# GET /v1/usage/me/subscriptions - Mes subscriptions actives
# ============================================================

@router.get("/me/subscriptions", response_model=list[ActiveSubscription])
async def get_my_active_subscriptions(
    current_user: User = Depends(get_current_user)
) -> list[ActiveSubscription]:
    """
    Retourne la liste des subscriptions actives de l'utilisateur.
    """
    user_id = current_user.id

    logger.info(f"Fetching active subscriptions for user={user_id}")

    # TODO: Remplacer par query DB subscriptions
    # Pour le MVP, retourner des données simulées

    now = datetime.utcnow()

    return [
        ActiveSubscription(
            id="sub-001",
            tool_id="crm-search",
            tool_name="CRM Customer Search",
            tool_description="Search and retrieve customer information from CRM",
            status="active",
            created_at=now - timedelta(days=30),
            last_used_at=now - timedelta(minutes=15),
            call_count_total=1250
        ),
        ActiveSubscription(
            id="sub-002",
            tool_id="billing-invoice",
            tool_name="Billing Invoice Generator",
            tool_description="Generate and send invoices to customers",
            status="active",
            created_at=now - timedelta(days=25),
            last_used_at=now - timedelta(hours=2),
            call_count_total=890
        ),
        ActiveSubscription(
            id="sub-003",
            tool_id="inventory-check",
            tool_name="Inventory Availability Check",
            tool_description="Check real-time inventory levels across warehouses",
            status="active",
            created_at=now - timedelta(days=20),
            last_used_at=now - timedelta(hours=1),
            call_count_total=654
        ),
        ActiveSubscription(
            id="sub-004",
            tool_id="notification-send",
            tool_name="Send Notification",
            tool_description="Send push/email/SMS notifications to users",
            status="active",
            created_at=now - timedelta(days=15),
            last_used_at=now - timedelta(days=1),
            call_count_total=412
        ),
    ]
