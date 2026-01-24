"""
Pydantic schemas for Usage API endpoints - CAB-280
Dashboard Usage Consumer pour DevOps/CPI
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CallStatus(str, Enum):
    """Status of an MCP tool call"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class UsagePeriodStats(BaseModel):
    """Statistics for a specific period"""
    period: str = Field(..., description="Period identifier (today, week, month)")
    total_calls: int = Field(..., ge=0, description="Total number of calls")
    success_count: int = Field(..., ge=0, description="Number of successful calls")
    error_count: int = Field(..., ge=0, description="Number of failed calls")
    success_rate: float = Field(..., ge=0, le=100, description="Success rate percentage")
    avg_latency_ms: int = Field(..., ge=0, description="Average latency in milliseconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "period": "today",
                "total_calls": 127,
                "success_count": 120,
                "error_count": 7,
                "success_rate": 94.5,
                "avg_latency_ms": 180
            }
        }
    )


class ToolUsageStat(BaseModel):
    """Usage statistics for a specific tool"""
    tool_id: str = Field(..., description="Tool identifier")
    tool_name: str = Field(..., description="Tool display name")
    call_count: int = Field(..., ge=0, description="Number of calls to this tool")
    success_rate: float = Field(..., ge=0, le=100, description="Success rate percentage")
    avg_latency_ms: int = Field(..., ge=0, description="Average latency in milliseconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tool_id": "crm-search",
                "tool_name": "CRM Customer Search",
                "call_count": 1250,
                "success_rate": 98.5,
                "avg_latency_ms": 120
            }
        }
    )


class DailyCallStat(BaseModel):
    """Daily call count for charts"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    calls: int = Field(..., ge=0, description="Number of calls on this date")


class UsageSummary(BaseModel):
    """Complete usage summary for a user"""
    tenant_id: str = Field(..., description="User's tenant ID")
    user_id: str = Field(..., description="User identifier")
    today: UsagePeriodStats = Field(..., description="Today's statistics")
    this_week: UsagePeriodStats = Field(..., description="This week's statistics")
    this_month: UsagePeriodStats = Field(..., description="This month's statistics")
    top_tools: List[ToolUsageStat] = Field(
        default_factory=list,
        description="Top 5 most used tools"
    )
    daily_calls: List[DailyCallStat] = Field(
        default_factory=list,
        description="Call counts for the last 7 days"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "team-alpha",
                "user_id": "alice",
                "today": {
                    "period": "today",
                    "total_calls": 127,
                    "success_count": 120,
                    "error_count": 7,
                    "success_rate": 94.5,
                    "avg_latency_ms": 180
                },
                "this_week": {
                    "period": "week",
                    "total_calls": 842,
                    "success_count": 810,
                    "error_count": 32,
                    "success_rate": 96.2,
                    "avg_latency_ms": 165
                },
                "this_month": {
                    "period": "month",
                    "total_calls": 3254,
                    "success_count": 3180,
                    "error_count": 74,
                    "success_rate": 97.7,
                    "avg_latency_ms": 158
                },
                "top_tools": [
                    {"tool_id": "crm-search", "tool_name": "CRM Search", "call_count": 1250, "success_rate": 98.5, "avg_latency_ms": 120}
                ],
                "daily_calls": [
                    {"date": "2026-01-06", "calls": 120},
                    {"date": "2026-01-07", "calls": 135}
                ]
            }
        }
    )


class UsageCall(BaseModel):
    """A single MCP tool call record"""
    id: str = Field(..., description="Unique call identifier")
    timestamp: datetime = Field(..., description="When the call was made")
    tool_id: str = Field(..., description="Tool identifier")
    tool_name: str = Field(..., description="Tool display name")
    status: CallStatus = Field(..., description="Call status")
    latency_ms: int = Field(..., ge=0, description="Call latency in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "call-0001",
                "timestamp": "2026-01-12T10:30:00Z",
                "tool_id": "crm-search",
                "tool_name": "CRM Customer Search",
                "status": "success",
                "latency_ms": 145,
                "error_message": None
            }
        }
    )


class UsageCallsResponse(BaseModel):
    """Paginated response for calls list"""
    calls: List[UsageCall] = Field(..., description="List of calls")
    total: int = Field(..., ge=0, description="Total number of calls matching filters")
    limit: int = Field(..., ge=1, description="Page size")
    offset: int = Field(..., ge=0, description="Offset from start")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "calls": [],
                "total": 247,
                "limit": 20,
                "offset": 0
            }
        }
    )


class ActiveSubscription(BaseModel):
    """An active tool subscription"""
    id: str = Field(..., description="Subscription identifier")
    tool_id: str = Field(..., description="Tool identifier")
    tool_name: str = Field(..., description="Tool display name")
    tool_description: Optional[str] = Field(None, description="Tool description")
    status: str = Field(..., description="Subscription status (active, suspended, expired)")
    created_at: datetime = Field(..., description="When subscription was created")
    last_used_at: Optional[datetime] = Field(None, description="When tool was last used")
    call_count_total: int = Field(default=0, ge=0, description="Total calls made via this subscription")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "sub-001",
                "tool_id": "crm-search",
                "tool_name": "CRM Customer Search",
                "tool_description": "Search and retrieve customer information from CRM",
                "status": "active",
                "created_at": "2025-12-12T10:00:00Z",
                "last_used_at": "2026-01-12T10:15:00Z",
                "call_count_total": 1250
            }
        }
    )


# ============ Dashboard Types (CAB-299) ============

class ActivityType(str, Enum):
    """Type of activity for the dashboard"""
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_APPROVED = "subscription.approved"
    SUBSCRIPTION_REVOKED = "subscription.revoked"
    API_CALL = "api.call"
    KEY_ROTATED = "key.rotated"


class DashboardStats(BaseModel):
    """Dashboard statistics for home page"""
    tools_available: int = Field(..., ge=0, description="Number of tools available")
    active_subscriptions: int = Field(..., ge=0, description="Number of active subscriptions")
    api_calls_this_week: int = Field(..., ge=0, description="API calls this week")
    tools_trend: Optional[float] = Field(None, description="Tools trend percentage")
    subscriptions_trend: Optional[float] = Field(None, description="Subscriptions trend percentage")
    calls_trend: Optional[float] = Field(None, description="Calls trend percentage")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tools_available": 12,
                "active_subscriptions": 4,
                "api_calls_this_week": 842,
                "tools_trend": 8.5,
                "subscriptions_trend": 25.0,
                "calls_trend": 12.3
            }
        }
    )


class RecentActivityItem(BaseModel):
    """A recent activity item for the dashboard"""
    id: str = Field(..., description="Activity identifier")
    type: ActivityType = Field(..., description="Type of activity")
    title: str = Field(..., description="Activity title")
    description: Optional[str] = Field(None, description="Activity description")
    tool_id: Optional[str] = Field(None, description="Related tool ID")
    tool_name: Optional[str] = Field(None, description="Related tool name")
    timestamp: datetime = Field(..., description="When the activity occurred")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "act-001",
                "type": "subscription.created",
                "title": "Subscribed to CRM Search",
                "description": "New subscription created",
                "tool_id": "crm-search",
                "tool_name": "CRM Customer Search",
                "timestamp": "2026-01-12T10:00:00Z"
            }
        }
    )


class DashboardActivityResponse(BaseModel):
    """Response for dashboard activity endpoint"""
    activity: List[RecentActivityItem] = Field(..., description="List of recent activities")
