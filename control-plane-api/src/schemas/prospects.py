# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Pydantic schemas for admin prospects endpoints (CAB-911)."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Type aliases
ProspectStatus = Literal["pending", "opened", "converted", "expired"]
NPSCategory = Literal["promoter", "passive", "detractor"]


# =============================================================================
# List Response Schemas
# =============================================================================


class ProspectSummary(BaseModel):
    """Summary of a prospect for list view."""

    id: UUID
    email: str
    company: str
    status: ProspectStatus
    source: Optional[str] = None
    created_at: datetime
    opened_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    time_to_first_tool_seconds: Optional[float] = Field(
        None, description="Seconds from first visit to first tool call"
    )
    nps_score: Optional[int] = Field(None, ge=1, le=10)
    nps_category: Optional[NPSCategory] = None
    total_events: int = 0

    model_config = {"from_attributes": True}


class ProspectListMeta(BaseModel):
    """Pagination metadata for list response."""

    total: int
    page: int
    limit: int


class ProspectListResponse(BaseModel):
    """Paginated list of prospects."""

    data: list[ProspectSummary]
    meta: ProspectListMeta


# =============================================================================
# Detail Response Schemas
# =============================================================================


class ProspectEventDetail(BaseModel):
    """Single event in the timeline."""

    id: UUID
    event_type: str
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)
    is_first_tool_call: bool = Field(
        False, description="True if this is the first tool_called event"
    )

    model_config = {"from_attributes": True}


class ProspectMetrics(BaseModel):
    """Calculated metrics for a prospect."""

    time_to_open_seconds: Optional[float] = Field(
        None, description="Seconds from invite creation to first visit"
    )
    time_to_first_tool_seconds: Optional[float] = Field(
        None, description="Seconds from first visit to first tool call"
    )
    tools_called_count: int = 0
    pages_viewed_count: int = 0
    errors_count: int = 0
    session_duration_seconds: Optional[float] = None


class ProspectDetail(BaseModel):
    """Detailed prospect information with timeline."""

    id: UUID
    email: str
    company: str
    status: ProspectStatus
    source: Optional[str] = None
    created_at: datetime
    opened_at: Optional[datetime] = None
    expires_at: datetime
    nps_score: Optional[int] = Field(None, ge=1, le=10)
    nps_category: Optional[NPSCategory] = None
    nps_comment: Optional[str] = None
    metrics: ProspectMetrics
    timeline: list[ProspectEventDetail] = Field(
        default_factory=list,
        description="Last 50 events, most recent first",
    )
    errors: list[ProspectEventDetail] = Field(
        default_factory=list,
        description="Error events only",
    )

    model_config = {"from_attributes": True}


# =============================================================================
# Metrics Response Schemas
# =============================================================================


class ConversionFunnel(BaseModel):
    """Conversion funnel metrics."""

    total_invites: int
    pending: int
    opened: int
    converted: int
    expired: int


class NPSDistribution(BaseModel):
    """NPS score distribution."""

    promoters: int = Field(0, description="Score 9-10")
    passives: int = Field(0, description="Score 7-8")
    detractors: int = Field(0, description="Score 1-6")
    no_response: int = Field(0, description="No feedback submitted")
    nps_score: float = Field(
        0, description="Calculated NPS (-100 to 100)"
    )
    avg_score: Optional[float] = Field(
        None, description="Average NPS score (1-10)"
    )


class TimingMetrics(BaseModel):
    """Average timing metrics."""

    avg_time_to_open_seconds: Optional[float] = None
    avg_time_to_first_tool_seconds: Optional[float] = None


class CompanyStats(BaseModel):
    """Stats for a company."""

    company: str
    invite_count: int
    converted_count: int


class ProspectsMetricsResponse(BaseModel):
    """Aggregated KPIs for prospects dashboard."""

    total_invited: int
    total_active: int = Field(
        0, description="Opened + converted (active prospects)"
    )
    avg_time_to_tool: Optional[float] = Field(
        None, description="Average seconds to first tool call"
    )
    avg_nps: Optional[float] = Field(None, description="Average NPS score")
    by_status: ConversionFunnel
    nps: NPSDistribution
    timing: TimingMetrics
    top_companies: list[CompanyStats] = Field(
        default_factory=list,
        description="Top 5 companies by invite count",
    )
