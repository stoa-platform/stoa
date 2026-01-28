# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Error Snapshot business logic service.

CAB-397: Handles capture, enrichment, and retrieval of error snapshots.
"""

import json
import logging
import os
import shlex
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request

from .config import SnapshotSettings
from .masking import PIIMasker
from .models import (
    BackendState,
    EnvironmentInfo,
    ErrorSnapshot,
    LogEntry,
    PolicyResult,
    RequestSnapshot,
    ResponseSnapshot,
    RoutingInfo,
    SnapshotFilters,
    SnapshotListResponse,
    SnapshotTrigger,
)
from .storage import SnapshotStorage

logger = logging.getLogger(__name__)


class SnapshotService:
    """Business logic for error snapshot capture and retrieval.

    Responsibilities:
    - Capture request/response data
    - Mask PII before storage
    - Enrich with environment info
    - Store and retrieve snapshots
    """

    def __init__(self, storage: SnapshotStorage, settings: SnapshotSettings):
        self.storage = storage
        self.settings = settings
        self.masker = PIIMasker(settings.masking_config)

    async def capture_error(
        self,
        request: Request,
        response_status: int,
        response_headers: dict[str, str],
        request_body: bytes | None,
        response_body: bytes | None,
        duration_ms: int,
        tenant_id: str,
        trigger: SnapshotTrigger,
        trace_id: str | None = None,
        routing: RoutingInfo | None = None,
        policies: list[PolicyResult] | None = None,
        backend_state: BackendState | None = None,
    ) -> ErrorSnapshot:
        """Capture and store an error snapshot.

        Args:
            request: Starlette Request object
            response_status: HTTP response status code
            response_headers: Response headers
            request_body: Raw request body bytes
            response_body: Raw response body bytes
            duration_ms: Request duration in milliseconds
            tenant_id: Tenant ID for isolation
            trigger: What triggered the capture
            trace_id: Optional trace ID for correlation
            routing: Optional routing info
            policies: Optional list of applied policies
            backend_state: Optional backend health state

        Returns:
            Created ErrorSnapshot
        """
        # Parse request headers
        req_headers = dict(request.headers)

        # Parse request body
        parsed_req_body = self._parse_body(request_body)

        # Parse response body
        parsed_resp_body = self._parse_body(response_body)

        # Get query params
        query_params = dict(request.query_params)

        # Mask sensitive data
        masked_req_headers, masked_req_body, masked_query, masked_fields = (
            self.masker.mask_snapshot_data(req_headers, parsed_req_body, query_params)
        )

        masked_resp_headers, masked_resp_body, _, resp_masked = (
            self.masker.mask_snapshot_data(response_headers, parsed_resp_body)
        )
        masked_fields.extend(resp_masked)

        # Build request snapshot
        request_snapshot = RequestSnapshot(
            method=request.method,
            path=str(request.url.path),
            headers=masked_req_headers,
            body=masked_req_body,
            query_params=masked_query or {},
            client_ip=self._get_client_ip(request),
            user_agent=req_headers.get("user-agent"),
        )

        # Build response snapshot
        response_snapshot = ResponseSnapshot(
            status=response_status,
            headers=masked_resp_headers,
            body=masked_resp_body,
            duration_ms=duration_ms,
        )

        # Build full snapshot
        snapshot = ErrorSnapshot(
            tenant_id=tenant_id,
            trigger=trigger,
            request=request_snapshot,
            response=response_snapshot,
            routing=routing or RoutingInfo(),
            policies_applied=policies or [],
            backend_state=backend_state or BackendState(),
            trace_id=trace_id,
            masked_fields=masked_fields,
        )

        # Enrich with environment
        self._enrich_with_environment(snapshot)

        # Store snapshot
        await self.storage.save(snapshot)

        logger.info(
            f"snapshot_captured snapshot_id={snapshot.id} tenant_id={tenant_id} "
            f"trigger={trigger.value} status={response_status} path={request.url.path} "
            f"duration_ms={duration_ms}"
        )

        return snapshot

    def _parse_body(self, body: bytes | None) -> Any:
        """Parse body bytes to JSON if possible, with size limits."""
        if not body:
            return None

        # Truncate if too large
        if len(body) > self.settings.max_body_size:
            return f"[TRUNCATED: {len(body)} bytes]"

        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Return as string if not JSON
            try:
                return body.decode("utf-8", errors="replace")
            except Exception:
                return f"[BINARY: {len(body)} bytes]"

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP from request, considering proxies."""
        # Check X-Forwarded-For first
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Return first IP in the chain
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to client host
        if request.client:
            return request.client.host

        return None

    def _enrich_with_environment(self, snapshot: ErrorSnapshot) -> None:
        """Add Kubernetes environment info from downward API.

        Expects environment variables:
        - HOSTNAME or POD_NAME: Pod name
        - NODE_NAME: Node name
        - POD_NAMESPACE: Namespace
        """
        snapshot.environment = EnvironmentInfo(
            pod=os.environ.get("HOSTNAME") or os.environ.get("POD_NAME"),
            node=os.environ.get("NODE_NAME"),
            namespace=os.environ.get("POD_NAMESPACE"),
            # Memory/CPU would require reading from cgroups or proc
            # Simplified for now
            memory_percent=None,
            cpu_percent=None,
        )

    async def enrich_with_logs(
        self,
        snapshot: ErrorSnapshot,
        query_func: Any = None,
    ) -> None:
        """Enrich snapshot with logs from around the error time.

        This is optional and depends on Loki/OpenSearch being available.
        The query_func should be provided by the caller if log enrichment
        is desired.

        Args:
            snapshot: Snapshot to enrich
            query_func: Optional async function to query logs
        """
        if not query_func:
            return

        try:
            # Query logs within window of error
            start_time = snapshot.timestamp.timestamp() - self.settings.log_window_seconds
            end_time = snapshot.timestamp.timestamp() + self.settings.log_window_seconds

            logs = await query_func(
                tenant_id=snapshot.tenant_id,
                trace_id=snapshot.trace_id,
                start_time=start_time,
                end_time=end_time,
                limit=self.settings.max_logs_per_snapshot,
            )

            snapshot.logs = [
                LogEntry(
                    timestamp=log.get("timestamp", datetime.now(timezone.utc)),
                    level=log.get("level", "INFO"),
                    message=log.get("message", ""),
                    extra=log.get("extra", {}),
                )
                for log in logs[:self.settings.max_logs_per_snapshot]
            ]

        except Exception as e:
            logger.warning(f"log_enrichment_failed: {e}")

    async def get(self, snapshot_id: str, tenant_id: str) -> ErrorSnapshot | None:
        """Get snapshot by ID with tenant isolation.

        Args:
            snapshot_id: Snapshot ID
            tenant_id: Tenant ID for access control

        Returns:
            ErrorSnapshot or None if not found/unauthorized
        """
        return await self.storage.get(snapshot_id, tenant_id)

    async def list(
        self,
        tenant_id: str,
        filters: SnapshotFilters,
        page: int = 1,
        page_size: int = 20,
    ) -> SnapshotListResponse:
        """List snapshots with pagination and filters.

        Args:
            tenant_id: Tenant ID for isolation
            filters: Filter criteria
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            SnapshotListResponse with items and pagination info
        """
        offset = (page - 1) * page_size

        items, total = await self.storage.list(
            tenant_id=tenant_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            limit=page_size,
            offset=offset,
        )

        # Apply additional filters that storage doesn't handle
        if filters.status_code:
            items = [i for i in items if i.status == filters.status_code]
            total = len(items)

        if filters.trigger:
            items = [i for i in items if i.trigger == filters.trigger]
            total = len(items)

        if filters.path_contains:
            items = [i for i in items if filters.path_contains in i.path]
            total = len(items)

        return SnapshotListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def delete(self, snapshot_id: str, tenant_id: str) -> bool:
        """Delete snapshot.

        Args:
            snapshot_id: Snapshot ID to delete
            tenant_id: Tenant ID for access control

        Returns:
            True if deleted, False if not found
        """
        return await self.storage.delete(snapshot_id, tenant_id)

    def generate_replay_curl(self, snapshot: ErrorSnapshot) -> str:
        """Generate cURL command to replay the captured request.

        Warning: This replays the MASKED request, so sensitive data
        will show as [REDACTED].

        Args:
            snapshot: Snapshot to generate replay for

        Returns:
            cURL command string
        """
        req = snapshot.request

        parts = ["curl", "-X", req.method]

        # Add headers (skip host, content-length)
        skip_headers = {"host", "content-length", "transfer-encoding"}
        for key, value in req.headers.items():
            if key.lower() not in skip_headers:
                parts.extend(["-H", f"{key}: {value}"])

        # Add body if present
        if req.body:
            if isinstance(req.body, dict):
                body_str = json.dumps(req.body)
            else:
                body_str = str(req.body)
            parts.extend(["-d", body_str])

        # Build URL with query params
        url = req.path
        if req.query_params:
            query = "&".join(f"{k}={v}" for k, v in req.query_params.items())
            url = f"{url}?{query}"

        parts.append(shlex.quote(url))

        return " ".join(parts)
