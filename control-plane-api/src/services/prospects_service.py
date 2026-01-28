# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Prospects service for admin dashboard (CAB-911).

Provides business logic for querying prospect data across the invites,
prospect_events, and prospect_feedback tables.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.invite import Invite, InviteStatus
from ..models.prospect_event import EventType, ProspectEvent
from ..models.prospect_feedback import ProspectFeedback
from ..schemas.prospects import (
    CompanyStats,
    ConversionFunnel,
    NPSDistribution,
    ProspectDetail,
    ProspectEventDetail,
    ProspectListMeta,
    ProspectListResponse,
    ProspectMetrics,
    ProspectsMetricsResponse,
    ProspectSummary,
    TimingMetrics,
)

logger = logging.getLogger(__name__)

# Timeline event limit (prevent loading huge event histories)
TIMELINE_LIMIT = 50


async def list_prospects(
    db: AsyncSession,
    company: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    limit: int = 25,
) -> ProspectListResponse:
    """List prospects with filters and pagination.

    Args:
        db: Database session
        company: Filter by company name (partial match, case-insensitive)
        status: Filter by status (pending, opened, converted, expired)
        date_from: Filter invites created after this date
        date_to: Filter invites created before this date
        page: Page number (1-indexed)
        limit: Items per page

    Returns:
        ProspectListResponse with data and pagination metadata
    """
    # Subquery for last activity timestamp
    last_activity_subq = (
        select(
            ProspectEvent.invite_id,
            func.max(ProspectEvent.timestamp).label("last_activity"),
        )
        .group_by(ProspectEvent.invite_id)
        .subquery()
    )

    # Subquery for first tool_called event timestamp
    first_tool_subq = (
        select(
            ProspectEvent.invite_id,
            func.min(ProspectEvent.timestamp).label("first_tool_at"),
        )
        .where(ProspectEvent.event_type == EventType.TOOL_CALLED.value)
        .group_by(ProspectEvent.invite_id)
        .subquery()
    )

    # Subquery for event count
    event_count_subq = (
        select(
            ProspectEvent.invite_id,
            func.count(ProspectEvent.id).label("event_count"),
        )
        .group_by(ProspectEvent.invite_id)
        .subquery()
    )

    # Main query with joins
    query = (
        select(
            Invite,
            ProspectFeedback.nps_score,
            ProspectFeedback.comment,
            last_activity_subq.c.last_activity,
            first_tool_subq.c.first_tool_at,
            event_count_subq.c.event_count,
        )
        .outerjoin(ProspectFeedback, Invite.id == ProspectFeedback.invite_id)
        .outerjoin(last_activity_subq, Invite.id == last_activity_subq.c.invite_id)
        .outerjoin(first_tool_subq, Invite.id == first_tool_subq.c.invite_id)
        .outerjoin(event_count_subq, Invite.id == event_count_subq.c.invite_id)
    )

    # Apply filters
    if company:
        query = query.where(Invite.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Invite.status == status)
    if date_from:
        query = query.where(Invite.created_at >= date_from)
    if date_to:
        query = query.where(Invite.created_at <= date_to)

    # Count total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination and ordering
    query = query.order_by(Invite.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # Transform to response
    prospects = []
    for row in rows:
        invite = row[0]
        nps_score = row[1]
        nps_comment = row[2]
        last_activity = row[3]
        first_tool_at = row[4]
        event_count = row[5] or 0

        # Calculate time to first tool (from opened_at to first_tool_at)
        time_to_first_tool = None
        if invite.opened_at and first_tool_at:
            delta = first_tool_at - invite.opened_at
            time_to_first_tool = delta.total_seconds()

        # Determine NPS category
        nps_category = None
        if nps_score is not None:
            if nps_score >= 9:
                nps_category = "promoter"
            elif nps_score >= 7:
                nps_category = "passive"
            else:
                nps_category = "detractor"

        prospects.append(
            ProspectSummary(
                id=invite.id,
                email=invite.email,
                company=invite.company,
                status=invite.status,
                source=invite.source,
                created_at=invite.created_at,
                opened_at=invite.opened_at,
                last_activity_at=last_activity,
                time_to_first_tool_seconds=time_to_first_tool,
                nps_score=nps_score,
                nps_category=nps_category,
                total_events=event_count,
            )
        )

    return ProspectListResponse(
        data=prospects,
        meta=ProspectListMeta(total=total, page=page, limit=limit),
    )


async def get_prospect_detail(
    db: AsyncSession,
    invite_id: UUID,
) -> Optional[ProspectDetail]:
    """Get detailed prospect info with timeline.

    Args:
        db: Database session
        invite_id: UUID of the invite

    Returns:
        ProspectDetail with metrics and timeline, or None if not found
    """
    # Get invite with feedback
    query = (
        select(Invite, ProspectFeedback)
        .outerjoin(ProspectFeedback, Invite.id == ProspectFeedback.invite_id)
        .where(Invite.id == invite_id)
    )
    result = await db.execute(query)
    row = result.first()

    if not row:
        return None

    invite, feedback = row

    # Get events (limited to TIMELINE_LIMIT, most recent first)
    events_query = (
        select(ProspectEvent)
        .where(ProspectEvent.invite_id == invite_id)
        .order_by(ProspectEvent.timestamp.desc())
        .limit(TIMELINE_LIMIT)
    )
    events_result = await db.execute(events_query)
    events = events_result.scalars().all()

    # Calculate metrics
    metrics = await _calculate_metrics(db, invite, events)

    # Find first tool call for marking in timeline
    first_tool_call_id = None
    for event in reversed(events):  # Oldest first to find the first
        if event.event_type == EventType.TOOL_CALLED.value:
            first_tool_call_id = event.id
            break

    # Transform events to timeline (errors separated)
    timeline = []
    errors = []
    for event in events:
        event_detail = ProspectEventDetail(
            id=event.id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            metadata=event.event_data,
            is_first_tool_call=event.id == first_tool_call_id,
        )
        if event.event_type == EventType.ERROR_ENCOUNTERED.value:
            errors.append(event_detail)
        timeline.append(event_detail)

    # Determine NPS category
    nps_category = None
    if feedback and feedback.nps_score is not None:
        if feedback.nps_score >= 9:
            nps_category = "promoter"
        elif feedback.nps_score >= 7:
            nps_category = "passive"
        else:
            nps_category = "detractor"

    return ProspectDetail(
        id=invite.id,
        email=invite.email,
        company=invite.company,
        status=invite.status,
        source=invite.source,
        created_at=invite.created_at,
        opened_at=invite.opened_at,
        expires_at=invite.expires_at,
        nps_score=feedback.nps_score if feedback else None,
        nps_category=nps_category,
        nps_comment=feedback.comment if feedback else None,
        metrics=metrics,
        timeline=timeline,
        errors=errors,
    )


async def _calculate_metrics(
    db: AsyncSession,
    invite: Invite,
    events: list[ProspectEvent],
) -> ProspectMetrics:
    """Calculate metrics for a prospect."""
    # Group events by type
    tools_called = 0
    pages_viewed = 0
    errors_count = 0
    first_tool_at = None
    last_event_at = None
    first_event_at = None

    for event in events:
        if event.event_type == EventType.TOOL_CALLED.value:
            tools_called += 1
            if first_tool_at is None or event.timestamp < first_tool_at:
                first_tool_at = event.timestamp
        elif event.event_type == EventType.PAGE_VIEWED.value:
            pages_viewed += 1
        elif event.event_type == EventType.ERROR_ENCOUNTERED.value:
            errors_count += 1

        if last_event_at is None or event.timestamp > last_event_at:
            last_event_at = event.timestamp
        if first_event_at is None or event.timestamp < first_event_at:
            first_event_at = event.timestamp

    # Calculate time metrics
    time_to_open = None
    if invite.opened_at:
        delta = invite.opened_at - invite.created_at
        time_to_open = delta.total_seconds()

    time_to_first_tool = None
    if invite.opened_at and first_tool_at:
        delta = first_tool_at - invite.opened_at
        time_to_first_tool = delta.total_seconds()

    session_duration = None
    if first_event_at and last_event_at:
        delta = last_event_at - first_event_at
        session_duration = delta.total_seconds()

    return ProspectMetrics(
        time_to_open_seconds=time_to_open,
        time_to_first_tool_seconds=time_to_first_tool,
        tools_called_count=tools_called,
        pages_viewed_count=pages_viewed,
        errors_count=errors_count,
        session_duration_seconds=session_duration,
    )


async def get_metrics(
    db: AsyncSession,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> ProspectsMetricsResponse:
    """Calculate aggregated KPIs for the dashboard.

    Args:
        db: Database session
        date_from: Filter invites created after this date
        date_to: Filter invites created before this date

    Returns:
        ProspectsMetricsResponse with aggregated metrics
    """
    # Base filter for invites
    base_filter = []
    if date_from:
        base_filter.append(Invite.created_at >= date_from)
    if date_to:
        base_filter.append(Invite.created_at <= date_to)

    # Funnel counts by status
    funnel_query = select(
        func.count(Invite.id).label("total"),
        func.sum(case((Invite.status == InviteStatus.PENDING.value, 1), else_=0)).label(
            "pending"
        ),
        func.sum(case((Invite.status == InviteStatus.OPENED.value, 1), else_=0)).label(
            "opened"
        ),
        func.sum(
            case((Invite.status == InviteStatus.CONVERTED.value, 1), else_=0)
        ).label("converted"),
        func.sum(
            case((Invite.status == InviteStatus.EXPIRED.value, 1), else_=0)
        ).label("expired"),
    )
    if base_filter:
        funnel_query = funnel_query.where(*base_filter)

    funnel_result = await db.execute(funnel_query)
    funnel_row = funnel_result.first()

    total_invites = funnel_row.total or 0
    pending = funnel_row.pending or 0
    opened = funnel_row.opened or 0
    converted = funnel_row.converted or 0
    expired = funnel_row.expired or 0

    # NPS distribution
    nps_query = select(
        func.count(ProspectFeedback.id).label("total_feedback"),
        func.sum(case((ProspectFeedback.nps_score >= 9, 1), else_=0)).label(
            "promoters"
        ),
        func.sum(
            case(
                (
                    (ProspectFeedback.nps_score >= 7)
                    & (ProspectFeedback.nps_score < 9),
                    1,
                ),
                else_=0,
            )
        ).label("passives"),
        func.sum(case((ProspectFeedback.nps_score < 7, 1), else_=0)).label("detractors"),
        func.avg(ProspectFeedback.nps_score).label("avg_score"),
    )
    if base_filter:
        # Join with invites to apply date filter
        nps_query = nps_query.join(
            Invite, ProspectFeedback.invite_id == Invite.id
        ).where(*base_filter)

    nps_result = await db.execute(nps_query)
    nps_row = nps_result.first()

    total_feedback = nps_row.total_feedback or 0
    promoters = nps_row.promoters or 0
    passives = nps_row.passives or 0
    detractors = nps_row.detractors or 0
    avg_score = float(nps_row.avg_score) if nps_row.avg_score else None

    # Calculate NPS score: ((promoters - detractors) / total) * 100
    nps_score = 0.0
    if total_feedback > 0:
        nps_score = ((promoters - detractors) / total_feedback) * 100

    no_response = total_invites - total_feedback

    # Timing metrics - average time to first tool
    # Subquery to get first tool call time per invite
    first_tool_subq = (
        select(
            ProspectEvent.invite_id,
            func.min(ProspectEvent.timestamp).label("first_tool_at"),
        )
        .where(ProspectEvent.event_type == EventType.TOOL_CALLED.value)
        .group_by(ProspectEvent.invite_id)
        .subquery()
    )

    timing_query = select(
        func.avg(
            func.extract(
                "epoch",
                first_tool_subq.c.first_tool_at - Invite.opened_at,
            )
        ).label("avg_time_to_tool"),
        func.avg(
            func.extract(
                "epoch",
                Invite.opened_at - Invite.created_at,
            )
        ).label("avg_time_to_open"),
    ).outerjoin(first_tool_subq, Invite.id == first_tool_subq.c.invite_id)

    if base_filter:
        timing_query = timing_query.where(*base_filter)
    # Only include invites that have been opened
    timing_query = timing_query.where(Invite.opened_at.isnot(None))

    timing_result = await db.execute(timing_query)
    timing_row = timing_result.first()

    avg_time_to_tool = (
        float(timing_row.avg_time_to_tool)
        if timing_row and timing_row.avg_time_to_tool
        else None
    )
    avg_time_to_open = (
        float(timing_row.avg_time_to_open)
        if timing_row and timing_row.avg_time_to_open
        else None
    )

    # Top companies
    companies_query = (
        select(
            Invite.company,
            func.count(Invite.id).label("invite_count"),
            func.sum(
                case((Invite.status == InviteStatus.CONVERTED.value, 1), else_=0)
            ).label("converted_count"),
        )
        .group_by(Invite.company)
        .order_by(func.count(Invite.id).desc())
        .limit(5)
    )
    if base_filter:
        companies_query = companies_query.where(*base_filter)

    companies_result = await db.execute(companies_query)
    top_companies = [
        CompanyStats(
            company=row.company,
            invite_count=row.invite_count,
            converted_count=row.converted_count or 0,
        )
        for row in companies_result.all()
    ]

    return ProspectsMetricsResponse(
        total_invited=total_invites,
        total_active=opened + converted,
        avg_time_to_tool=avg_time_to_tool,
        avg_nps=avg_score,
        by_status=ConversionFunnel(
            total_invites=total_invites,
            pending=pending,
            opened=opened,
            converted=converted,
            expired=expired,
        ),
        nps=NPSDistribution(
            promoters=promoters,
            passives=passives,
            detractors=detractors,
            no_response=no_response,
            nps_score=nps_score,
            avg_score=avg_score,
        ),
        timing=TimingMetrics(
            avg_time_to_open_seconds=avg_time_to_open,
            avg_time_to_first_tool_seconds=avg_time_to_tool,
        ),
        top_companies=top_companies,
    )


async def export_prospects_csv(
    db: AsyncSession,
    company: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> str:
    """Export prospects to CSV format.

    Args:
        db: Database session
        company: Filter by company name
        status: Filter by status
        date_from: Filter by start date
        date_to: Filter by end date

    Returns:
        CSV content as string
    """
    # Subquery for first tool_called event timestamp
    first_tool_subq = (
        select(
            ProspectEvent.invite_id,
            func.min(ProspectEvent.timestamp).label("first_tool_at"),
        )
        .where(ProspectEvent.event_type == EventType.TOOL_CALLED.value)
        .group_by(ProspectEvent.invite_id)
        .subquery()
    )

    # Main query
    query = (
        select(
            Invite,
            ProspectFeedback.nps_score,
            ProspectFeedback.comment,
            first_tool_subq.c.first_tool_at,
        )
        .outerjoin(ProspectFeedback, Invite.id == ProspectFeedback.invite_id)
        .outerjoin(first_tool_subq, Invite.id == first_tool_subq.c.invite_id)
    )

    # Apply filters
    if company:
        query = query.where(Invite.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Invite.status == status)
    if date_from:
        query = query.where(Invite.created_at >= date_from)
    if date_to:
        query = query.where(Invite.created_at <= date_to)

    query = query.order_by(Invite.created_at.desc())

    result = await db.execute(query)
    rows = result.all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "ID",
            "Email",
            "Company",
            "Status",
            "Source",
            "Created At",
            "Opened At",
            "Time to First Tool (seconds)",
            "NPS Score",
            "NPS Comment",
        ]
    )

    # Data rows
    for row in rows:
        invite = row[0]
        nps_score = row[1]
        nps_comment = row[2]
        first_tool_at = row[3]

        # Calculate time to first tool
        time_to_tool = ""
        if invite.opened_at and first_tool_at:
            delta = first_tool_at - invite.opened_at
            time_to_tool = str(int(delta.total_seconds()))

        writer.writerow(
            [
                str(invite.id),
                invite.email,
                invite.company,
                invite.status,
                invite.source or "",
                invite.created_at.isoformat(),
                invite.opened_at.isoformat() if invite.opened_at else "",
                time_to_tool,
                str(nps_score) if nps_score else "",
                nps_comment or "",
            ]
        )

    return output.getvalue()
