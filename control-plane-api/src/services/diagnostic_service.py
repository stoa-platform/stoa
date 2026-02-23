"""Diagnostic service with rule-based auto-RCA (CAB-1316).

Classifies execution log errors into diagnostic categories with
confidence scores. No ML — taxonomy-first approach per Council mandate.
"""

import socket
import ssl
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus
from src.models.gateway_instance import GatewayInstance
from src.schemas.diagnostic import (
    ConnectivityResult,
    ConnectivityStage,
    DiagnosticCategory,
    DiagnosticListResponse,
    DiagnosticReport,
    RequestSummary,
    RootCause,
    TimingBreakdown,
)


class DiagnosticService:
    """Rule-based diagnostic engine for gateway error analysis."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def diagnose(
        self,
        tenant_id: str,
        gateway_id: str,
        request_id: str | None = None,
        time_range_minutes: int = 60,
    ) -> DiagnosticReport:
        """Run auto-RCA on recent execution logs for a gateway."""
        since = datetime.now(UTC) - timedelta(minutes=time_range_minutes)

        conditions = [
            ExecutionLog.tenant_id == tenant_id,
            ExecutionLog.status != ExecutionStatus.SUCCESS,
            ExecutionLog.started_at >= since,
        ]
        if request_id:
            conditions = [ExecutionLog.request_id == request_id]

        query = select(ExecutionLog).where(and_(*conditions)).order_by(ExecutionLog.started_at.desc()).limit(100)
        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        root_causes = self._classify_errors(logs)
        timing = self._aggregate_timing(logs)
        request_summary = self._build_request_summary(logs[0]) if logs else None

        return DiagnosticReport(
            tenant_id=tenant_id,
            gateway_id=gateway_id,
            root_causes=sorted(root_causes, key=lambda r: r.confidence, reverse=True),
            timing=timing,
            request_summary=request_summary,
            error_count=len(logs),
            time_range_minutes=time_range_minutes,
        )

    async def check_connectivity(self, tenant_id: str, gateway_id: str) -> ConnectivityResult:
        """Test connectivity chain: DNS → TCP → TLS → HTTP health."""
        gateway = await self._get_gateway(gateway_id)
        if not gateway:
            return ConnectivityResult(
                gateway_id=gateway_id,
                overall_status="unhealthy",
                stages=[ConnectivityStage(name="lookup", status="error", error="Gateway not found")],
            )

        stages: list[ConnectivityStage] = []
        base_url = str(gateway.base_url)

        # Parse host from base_url
        try:
            parsed = httpx.URL(base_url)
            host = str(parsed.host)
            port = parsed.port or (443 if str(parsed.scheme) == "https" else 80)
            is_https = str(parsed.scheme) == "https"
        except Exception as e:
            stages.append(ConnectivityStage(name="url_parse", status="error", error=str(e)))
            return ConnectivityResult(gateway_id=gateway_id, overall_status="unhealthy", stages=stages)

        # Stage 1: DNS resolution
        dns_start = time.monotonic()
        try:
            socket.getaddrinfo(host, port)
            dns_ms = (time.monotonic() - dns_start) * 1000
            stages.append(ConnectivityStage(name="dns", status="ok", latency_ms=round(dns_ms, 2)))
        except socket.gaierror as e:
            dns_ms = (time.monotonic() - dns_start) * 1000
            stages.append(ConnectivityStage(name="dns", status="error", latency_ms=round(dns_ms, 2), error=str(e)))
            return ConnectivityResult(gateway_id=gateway_id, overall_status="unhealthy", stages=stages)

        # Stage 2: TCP connect
        tcp_start = time.monotonic()
        try:
            sock = socket.create_connection((host, port), timeout=5)
            tcp_ms = (time.monotonic() - tcp_start) * 1000
            stages.append(ConnectivityStage(name="tcp", status="ok", latency_ms=round(tcp_ms, 2)))
            sock.close()
        except (OSError, TimeoutError) as e:
            tcp_ms = (time.monotonic() - tcp_start) * 1000
            stages.append(ConnectivityStage(name="tcp", status="error", latency_ms=round(tcp_ms, 2), error=str(e)))
            return ConnectivityResult(gateway_id=gateway_id, overall_status="unhealthy", stages=stages)

        # Stage 3: TLS handshake (if HTTPS)
        if is_https:
            tls_start = time.monotonic()
            try:
                ctx = ssl.create_default_context()
                with socket.create_connection((host, port), timeout=5) as raw_sock:
                    ctx.wrap_socket(raw_sock, server_hostname=host)
                tls_ms = (time.monotonic() - tls_start) * 1000
                stages.append(ConnectivityStage(name="tls", status="ok", latency_ms=round(tls_ms, 2)))
            except (ssl.SSLError, OSError) as e:
                tls_ms = (time.monotonic() - tls_start) * 1000
                stages.append(ConnectivityStage(name="tls", status="error", latency_ms=round(tls_ms, 2), error=str(e)))
                return ConnectivityResult(gateway_id=gateway_id, overall_status="unhealthy", stages=stages)

        # Stage 4: HTTP health check
        health_url = f"{base_url.rstrip('/')}/health"
        http_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:  # noqa: S501
                resp = await client.get(health_url)
                http_ms = (time.monotonic() - http_start) * 1000
                status = "ok" if resp.status_code < 400 else "error"
                stages.append(
                    ConnectivityStage(
                        name="http_health",
                        status=status,
                        latency_ms=round(http_ms, 2),
                        error=f"HTTP {resp.status_code}" if resp.status_code >= 400 else None,
                    )
                )
        except httpx.HTTPError as e:
            http_ms = (time.monotonic() - http_start) * 1000
            stages.append(
                ConnectivityStage(name="http_health", status="error", latency_ms=round(http_ms, 2), error=str(e))
            )

        has_error = any(s.status == "error" for s in stages)
        overall = "unhealthy" if has_error else "healthy"
        return ConnectivityResult(gateway_id=gateway_id, overall_status=overall, stages=stages)

    async def get_history(self, tenant_id: str, gateway_id: str, limit: int = 20) -> DiagnosticListResponse:
        """Return recent error logs as lightweight diagnostic entries."""
        query = (
            select(ExecutionLog)
            .where(
                and_(
                    ExecutionLog.tenant_id == tenant_id,
                    ExecutionLog.status != ExecutionStatus.SUCCESS,
                )
            )
            .order_by(ExecutionLog.started_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        reports = []
        for log in logs:
            causes = self._classify_errors([log])
            reports.append(
                DiagnosticReport(
                    tenant_id=tenant_id,
                    gateway_id=gateway_id,
                    root_causes=causes,
                    timing=TimingBreakdown(total_ms=float(log.duration_ms) if log.duration_ms else None),
                    request_summary=self._build_request_summary(log),
                    error_count=1,
                    time_range_minutes=0,
                )
            )
        return DiagnosticListResponse(items=reports, total=len(reports))

    def _classify_errors(self, logs: list[ExecutionLog]) -> list[RootCause]:
        """Rule-based error classification against the diagnostic taxonomy."""
        causes: dict[DiagnosticCategory, RootCause] = {}

        for log in logs:
            cause = self._classify_single(log)
            if cause and cause.category not in causes:
                causes[cause.category] = cause
            elif cause and cause.category in causes:
                existing = causes[cause.category]
                existing.evidence.extend(cause.evidence)
                existing.confidence = max(existing.confidence, cause.confidence)

        return list(causes.values())

    def _classify_single(self, log: ExecutionLog) -> RootCause | None:
        """Classify a single execution log entry.

        Priority: explicit error_category > message patterns > status code.
        This ensures specific categories (certificate, policy) aren't masked
        by ambiguous status codes (403 = auth OR policy, 502 = backend OR cert).
        """
        status = log.status_code
        category = log.error_category
        msg = (log.error_message or "").lower()

        # --- Phase 1: Explicit error_category (highest priority) ---

        if category == ErrorCategory.CIRCUIT_BREAKER:
            return RootCause(
                category=DiagnosticCategory.CIRCUIT_BREAKER,
                confidence=0.95,
                summary="Circuit breaker is open — backend marked unhealthy",
                evidence=[f"Circuit breaker rejection: {log.error_message or 'CB open'}"],
                suggested_fix="Check backend health; circuit will auto-recover after reset timeout",
            )

        if category == ErrorCategory.CERTIFICATE:
            return RootCause(
                category=DiagnosticCategory.CERTIFICATE,
                confidence=0.9,
                summary="TLS/certificate error in connection chain",
                evidence=[f"Certificate issue: {log.error_message or 'TLS error'}"],
                suggested_fix="Check certificate validity, chain, and expiry dates",
            )

        if category == ErrorCategory.POLICY:
            return RootCause(
                category=DiagnosticCategory.POLICY,
                confidence=0.9,
                summary="Request denied by policy engine or guardrails",
                evidence=[f"Policy denial: {log.error_message or 'policy blocked'}"],
                suggested_fix="Review gateway policies and guardrail rules for this API/tenant",
            )

        if category == ErrorCategory.RATE_LIMIT:
            return RootCause(
                category=DiagnosticCategory.RATE_LIMIT,
                confidence=0.95,
                summary="Rate limit or quota exceeded",
                evidence=[f"HTTP {status}: {log.error_message or 'rate limited'}"],
                suggested_fix="Reduce request rate or increase quota allocation",
            )

        if category == ErrorCategory.NETWORK:
            return RootCause(
                category=DiagnosticCategory.CONNECTIVITY,
                confidence=0.8,
                summary="Network connectivity failure",
                evidence=[f"Network error: {log.error_message or 'network issue'}"],
                suggested_fix="Check DNS resolution, firewall rules, and network connectivity",
            )

        if category == ErrorCategory.TIMEOUT:
            duration_info = f" (duration: {log.duration_ms}ms)" if log.duration_ms else ""
            return RootCause(
                category=DiagnosticCategory.CONNECTIVITY,
                confidence=0.8,
                summary=f"Request timed out{duration_info}",
                evidence=[f"HTTP {status}: {log.error_message or 'timeout'}{duration_info}"],
                suggested_fix="Check network path between gateway and backend; consider increasing timeout",
            )

        if category == ErrorCategory.AUTH:
            return RootCause(
                category=DiagnosticCategory.AUTH,
                confidence=0.9,
                summary="Authentication or authorization failure",
                evidence=[f"HTTP {status}: {log.error_message or 'auth error'}"],
                suggested_fix="Check JWT token validity, API key, or RBAC permissions",
            )

        if category == ErrorCategory.BACKEND:
            return RootCause(
                category=DiagnosticCategory.BACKEND,
                confidence=0.85,
                summary="Backend service unavailable or erroring",
                evidence=[f"HTTP {status}: {log.error_message or 'backend error'}"],
                suggested_fix="Verify backend service is running and accessible from the gateway",
            )

        # --- Phase 2: Message-pattern heuristics ---

        if "circuit" in msg:
            return RootCause(
                category=DiagnosticCategory.CIRCUIT_BREAKER,
                confidence=0.95,
                summary="Circuit breaker is open — backend marked unhealthy",
                evidence=[f"Circuit breaker rejection: {log.error_message or 'CB open'}"],
                suggested_fix="Check backend health; circuit will auto-recover after reset timeout",
            )

        if "tls" in msg or "certificate" in msg or "ssl" in msg:
            return RootCause(
                category=DiagnosticCategory.CERTIFICATE,
                confidence=0.9,
                summary="TLS/certificate error in connection chain",
                evidence=[f"Certificate issue: {log.error_message or 'TLS error'}"],
                suggested_fix="Check certificate validity, chain, and expiry dates",
            )

        if "policy" in msg or "guardrail" in msg or "denied" in msg:
            return RootCause(
                category=DiagnosticCategory.POLICY,
                confidence=0.9,
                summary="Request denied by policy engine or guardrails",
                evidence=[f"Policy denial: {log.error_message or 'policy blocked'}"],
                suggested_fix="Review gateway policies and guardrail rules for this API/tenant",
            )

        if "dns" in msg or "connection refused" in msg:
            return RootCause(
                category=DiagnosticCategory.CONNECTIVITY,
                confidence=0.8,
                summary="Network connectivity failure",
                evidence=[f"Network error: {log.error_message or 'network issue'}"],
                suggested_fix="Check DNS resolution, firewall rules, and network connectivity",
            )

        # --- Phase 3: Status-code fallback ---

        if status == 429:
            return RootCause(
                category=DiagnosticCategory.RATE_LIMIT,
                confidence=0.95,
                summary="Rate limit or quota exceeded",
                evidence=[f"HTTP 429: {log.error_message or 'rate limited'}"],
                suggested_fix="Reduce request rate or increase quota allocation",
            )

        if status in (401, 403):
            return RootCause(
                category=DiagnosticCategory.AUTH,
                confidence=0.9,
                summary="Authentication or authorization failure",
                evidence=[f"HTTP {status}: {log.error_message or 'auth error'}"],
                suggested_fix="Check JWT token validity, API key, or RBAC permissions",
            )

        if status == 504:
            duration_info = f" (duration: {log.duration_ms}ms)" if log.duration_ms else ""
            return RootCause(
                category=DiagnosticCategory.CONNECTIVITY,
                confidence=0.8,
                summary=f"Request timed out{duration_info}",
                evidence=[f"HTTP 504: {log.error_message or 'timeout'}{duration_info}"],
                suggested_fix="Check network path between gateway and backend; consider increasing timeout",
            )

        if status in (502, 503):
            return RootCause(
                category=DiagnosticCategory.BACKEND,
                confidence=0.85,
                summary="Backend service unavailable or erroring",
                evidence=[f"HTTP {status}: {log.error_message or 'backend error'}"],
                suggested_fix="Verify backend service is running and accessible from the gateway",
            )

        if status and status >= 500:
            return RootCause(
                category=DiagnosticCategory.BACKEND,
                confidence=0.6,
                summary=f"Server error (HTTP {status})",
                evidence=[f"HTTP {status}: {log.error_message or 'server error'}"],
                suggested_fix="Check backend logs for the root cause",
            )

        return None

    def _aggregate_timing(self, logs: list[ExecutionLog]) -> TimingBreakdown:
        """Aggregate timing from execution logs."""
        durations = [log.duration_ms for log in logs if log.duration_ms]
        if not durations:
            return TimingBreakdown()
        avg_ms = sum(durations) / len(durations)
        return TimingBreakdown(total_ms=round(avg_ms, 2))

    def _build_request_summary(self, log: ExecutionLog) -> RequestSummary:
        """Build a GDPR-redacted request summary (no body, no headers)."""
        return RequestSummary(
            method=log.method,
            path=log.path,
            status_code=log.status_code,
            request_id=log.request_id,
        )

    async def _get_gateway(self, gateway_id: str) -> GatewayInstance | None:
        """Fetch gateway instance by ID."""
        from uuid import UUID

        try:
            gw_uuid = UUID(gateway_id)
        except ValueError:
            return None
        result = await self.db.execute(select(GatewayInstance).where(GatewayInstance.id == gw_uuid))
        return result.scalar_one_or_none()
