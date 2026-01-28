# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
MCP Error Snapshot Repository

Database operations for error snapshots.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Tuple

import structlog
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.error_snapshot import ErrorSnapshotModel, ResolutionStatus
from .models import MCPErrorSnapshot

logger = structlog.get_logger(__name__)


class ErrorSnapshotRepository:
    """Repository for error snapshot CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, snapshot: MCPErrorSnapshot) -> ErrorSnapshotModel:
        """Save a new error snapshot to the database."""
        model = ErrorSnapshotModel.from_pydantic(snapshot)
        self.session.add(model)
        await self.session.flush()
        logger.info(
            "snapshot_saved",
            snapshot_id=model.id,
            error_type=model.error_type,
        )
        return model

    async def get_by_id(self, snapshot_id: str) -> Optional[ErrorSnapshotModel]:
        """Get a snapshot by ID."""
        result = await self.session.execute(
            select(ErrorSnapshotModel).where(ErrorSnapshotModel.id == snapshot_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        error_types: Optional[list[str]] = None,
        status_codes: Optional[list[int]] = None,
        server_names: Optional[list[str]] = None,
        tool_names: Optional[list[str]] = None,
        resolution_statuses: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_cost_usd: Optional[float] = None,
        search: Optional[str] = None,
    ) -> tuple[list[ErrorSnapshotModel], int]:
        """List snapshots with filters and pagination.

        Returns tuple of (snapshots, total_count).
        """
        # Build base query
        query = select(ErrorSnapshotModel)
        count_query = select(func.count(ErrorSnapshotModel.id))

        # Build filters
        filters = []

        if error_types:
            filters.append(ErrorSnapshotModel.error_type.in_(error_types))

        if status_codes:
            filters.append(ErrorSnapshotModel.response_status.in_(status_codes))

        if server_names:
            filters.append(ErrorSnapshotModel.mcp_server_name.in_(server_names))

        if tool_names:
            filters.append(ErrorSnapshotModel.tool_name.in_(tool_names))

        if resolution_statuses:
            status_enums = [ResolutionStatus(s) for s in resolution_statuses]
            filters.append(ErrorSnapshotModel.resolution_status.in_(status_enums))

        if tenant_id:
            filters.append(ErrorSnapshotModel.tenant_id == tenant_id)

        if user_id:
            filters.append(ErrorSnapshotModel.user_id == user_id)

        if start_date:
            filters.append(ErrorSnapshotModel.timestamp >= start_date)

        if end_date:
            filters.append(ErrorSnapshotModel.timestamp <= end_date)

        if min_cost_usd is not None:
            filters.append(ErrorSnapshotModel.total_cost_usd >= min_cost_usd)

        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    ErrorSnapshotModel.error_message.ilike(search_pattern),
                    ErrorSnapshotModel.tool_name.ilike(search_pattern),
                    ErrorSnapshotModel.mcp_server_name.ilike(search_pattern),
                    ErrorSnapshotModel.request_path.ilike(search_pattern),
                )
            )

        # Apply filters
        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Apply ordering and pagination
        offset = (page - 1) * page_size
        query = query.order_by(desc(ErrorSnapshotModel.timestamp))
        query = query.offset(offset).limit(page_size)

        # Execute query
        result = await self.session.execute(query)
        snapshots = list(result.scalars().all())

        return snapshots, total

    async def get_stats(
        self,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get aggregated statistics for snapshots."""
        # Build base filters
        filters = []
        if tenant_id:
            filters.append(ErrorSnapshotModel.tenant_id == tenant_id)
        if start_date:
            filters.append(ErrorSnapshotModel.timestamp >= start_date)
        if end_date:
            filters.append(ErrorSnapshotModel.timestamp <= end_date)

        base_filter = and_(*filters) if filters else True

        # Total count
        total_query = select(func.count(ErrorSnapshotModel.id)).where(base_filter)
        total_result = await self.session.execute(total_query)
        total = total_result.scalar() or 0

        # Count by error type
        by_type_query = (
            select(
                ErrorSnapshotModel.error_type,
                func.count(ErrorSnapshotModel.id).label("count"),
            )
            .where(base_filter)
            .group_by(ErrorSnapshotModel.error_type)
        )
        by_type_result = await self.session.execute(by_type_query)
        by_error_type = {row.error_type: row.count for row in by_type_result}

        # Count by status code
        by_status_query = (
            select(
                ErrorSnapshotModel.response_status,
                func.count(ErrorSnapshotModel.id).label("count"),
            )
            .where(base_filter)
            .group_by(ErrorSnapshotModel.response_status)
        )
        by_status_result = await self.session.execute(by_status_query)
        by_status = {row.response_status: row.count for row in by_status_result}

        # Count by server
        by_server_query = (
            select(
                ErrorSnapshotModel.mcp_server_name,
                func.count(ErrorSnapshotModel.id).label("count"),
            )
            .where(base_filter)
            .where(ErrorSnapshotModel.mcp_server_name.isnot(None))
            .group_by(ErrorSnapshotModel.mcp_server_name)
        )
        by_server_result = await self.session.execute(by_server_query)
        by_server = {row.mcp_server_name: row.count for row in by_server_result}

        # Sum costs and tokens
        cost_query = (
            select(
                func.coalesce(func.sum(ErrorSnapshotModel.total_cost_usd), 0.0).label("total_cost"),
                func.coalesce(func.sum(ErrorSnapshotModel.tokens_wasted), 0).label("total_tokens"),
                func.coalesce(func.avg(ErrorSnapshotModel.total_cost_usd), 0.0).label("avg_cost"),
            )
            .where(base_filter)
        )
        cost_result = await self.session.execute(cost_query)
        cost_row = cost_result.one()

        # Resolution stats
        resolution_query = (
            select(
                ErrorSnapshotModel.resolution_status,
                func.count(ErrorSnapshotModel.id).label("count"),
            )
            .where(base_filter)
            .group_by(ErrorSnapshotModel.resolution_status)
        )
        resolution_result = await self.session.execute(resolution_query)
        resolution_stats = {
            "unresolved": 0,
            "investigating": 0,
            "resolved": 0,
            "ignored": 0,
        }
        for row in resolution_result:
            resolution_stats[row.resolution_status.value] = row.count

        return {
            "total": total,
            "by_error_type": by_error_type,
            "by_status": by_status,
            "by_server": by_server,
            "total_cost_usd": float(cost_row.total_cost),
            "total_tokens_wasted": int(cost_row.total_tokens),
            "avg_cost_usd": float(cost_row.avg_cost),
            "resolution_stats": resolution_stats,
        }

    async def update_resolution(
        self,
        snapshot_id: str,
        status: ResolutionStatus,
        notes: Optional[str] = None,
        resolved_by: Optional[str] = None,
    ) -> Optional[ErrorSnapshotModel]:
        """Update resolution status of a snapshot."""
        snapshot = await self.get_by_id(snapshot_id)
        if not snapshot:
            return None

        snapshot.resolution_status = status
        if notes is not None:
            snapshot.resolution_notes = notes
        if resolved_by:
            snapshot.resolved_by = resolved_by

        if status == ResolutionStatus.RESOLVED:
            snapshot.resolved_at = datetime.now(timezone.utc)

        await self.session.flush()

        logger.info(
            "snapshot_resolution_updated",
            snapshot_id=snapshot_id,
            status=status.value,
        )
        return snapshot

    async def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot by ID."""
        snapshot = await self.get_by_id(snapshot_id)
        if not snapshot:
            return False

        await self.session.delete(snapshot)
        await self.session.flush()

        logger.info("snapshot_deleted", snapshot_id=snapshot_id)
        return True

    async def get_distinct_servers(self) -> list[str]:
        """Get list of distinct MCP server names."""
        query = (
            select(ErrorSnapshotModel.mcp_server_name)
            .where(ErrorSnapshotModel.mcp_server_name.isnot(None))
            .distinct()
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]

    async def get_distinct_tools(self) -> list[str]:
        """Get list of distinct tool names."""
        query = (
            select(ErrorSnapshotModel.tool_name)
            .where(ErrorSnapshotModel.tool_name.isnot(None))
            .distinct()
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]
