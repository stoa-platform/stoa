"""Security Aggregation Service — unifies 3 data sources for Security Posture (CAB-2008).

Aggregates:
1. OpenSearch audit-* indices (auth failures, rate limits, policy violations)
2. PostgreSQL security_events table (Kafka-fed DORA alerts)
3. PostgreSQL security_findings table (scanner push model)

Into a single score + findings response with data freshness indicators.
"""

import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.security_event import SecurityEvent
from ..models.security_finding import SecurityFinding, SecurityScan
from ..schemas.security_posture import (
    DataFreshness,
    DataFreshnessSource,
    FindingSeverity,
    FindingsListResponse,
    SecurityFindingResponse,
    SecurityScoreResponse,
    SeverityBreakdown,
)

logger = logging.getLogger(__name__)

# Severity weights for score calculation (same as SecurityScannerService)
_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 5.0,
    "medium": 2.0,
    "low": 0.5,
    "info": 0.0,
}

# OpenSearch severity → normalized 5-level scale
_OS_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "error": "high",
    "warning": "medium",
    "info": "info",
}

# Max events to fetch from OpenSearch for findings listing
_OS_MAX_FINDINGS = 1000


class SecurityAggregationService:
    """Aggregates security data from OpenSearch + PG security_events + PG security_findings."""

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    async def calculate_aggregated_score(
        self,
        tenant_id: str,
        db: AsyncSession,
        os_client: object | None = None,
    ) -> SecurityScoreResponse:
        """Calculate security score aggregating all 3 sources."""
        severity_counts: dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
        }

        # Source freshness tracking
        os_source = DataFreshnessSource()
        pg_events_source = DataFreshnessSource()
        pg_findings_source = DataFreshnessSource()

        # --- 1. OpenSearch audit-* aggregation ---
        if os_client is not None:
            try:
                os_counts, os_last, os_total = await self._query_os_severity_aggs(os_client, tenant_id)
                for sev, count in os_counts.items():
                    normalized = _OS_SEVERITY_MAP.get(sev, "info")
                    severity_counts[normalized] = severity_counts.get(normalized, 0) + count
                os_source.count = os_total
                os_source.last_event_at = os_last
            except Exception:
                logger.warning("OpenSearch unavailable for score aggregation", exc_info=True)
                os_source.count = -1

        # --- 2. PG security_events ---
        try:
            pg_evt_result = await db.execute(
                select(
                    SecurityEvent.severity,
                    func.count(SecurityEvent.id).label("cnt"),
                )
                .where(SecurityEvent.tenant_id == tenant_id)
                .group_by(SecurityEvent.severity)
            )
            for row in pg_evt_result.all():
                normalized = _OS_SEVERITY_MAP.get(row.severity, row.severity)
                severity_counts[normalized] = severity_counts.get(normalized, 0) + row.cnt

            # Count + last event
            pg_evt_meta = await db.execute(
                select(
                    func.count(SecurityEvent.id),
                    func.max(SecurityEvent.created_at),
                ).where(SecurityEvent.tenant_id == tenant_id)
            )
            meta_row = pg_evt_meta.one()
            pg_events_source.count = meta_row[0] or 0
            pg_events_source.last_event_at = meta_row[1]
        except Exception:
            logger.warning("Failed to query security_events", exc_info=True)

        # --- 3. PG security_findings (existing scanner data) ---
        try:
            findings_result = await db.execute(
                select(
                    SecurityFinding.severity,
                    func.count(SecurityFinding.id).label("cnt"),
                )
                .where(
                    SecurityFinding.tenant_id == tenant_id,
                    SecurityFinding.status == "open",
                )
                .group_by(SecurityFinding.severity)
            )
            for row in findings_result.all():
                severity_counts[row.severity] = severity_counts.get(row.severity, 0) + row.cnt

            findings_meta = await db.execute(
                select(
                    func.count(SecurityFinding.id),
                    func.max(SecurityFinding.created_at),
                ).where(SecurityFinding.tenant_id == tenant_id)
            )
            fmeta = findings_meta.one()
            pg_findings_source.count = fmeta[0] or 0
            pg_findings_source.last_event_at = fmeta[1]
        except Exception:
            logger.warning("Failed to query security_findings", exc_info=True)

        # --- Compute score ---
        has_any_data = (os_source.count or 0) > 0 or pg_events_source.count > 0 or pg_findings_source.count > 0

        if not has_any_data:
            # No data from any source = unknown posture = 0
            score = 0.0
        else:
            penalty = sum(_SEVERITY_WEIGHTS.get(sev, 0) * count for sev, count in severity_counts.items())
            score = max(0.0, 100.0 - penalty)

        # Open findings count (only from severity_counts, which already filtered open)
        open_findings = sum(severity_counts.values())

        # Total findings (all statuses from PG security_findings)
        total_findings_result = await db.execute(
            select(func.count(SecurityFinding.id)).where(SecurityFinding.tenant_id == tenant_id)
        )
        total_findings = total_findings_result.scalar_one()
        total_findings += pg_events_source.count + max(os_source.count, 0)

        # Last scan
        scan_result = await db.execute(
            select(SecurityScan.completed_at, SecurityScan.score)
            .where(
                SecurityScan.tenant_id == tenant_id,
                SecurityScan.status == "completed",
            )
            .order_by(SecurityScan.completed_at.desc())
            .limit(2)
        )
        scans = scan_result.all()
        last_scan_at = scans[0].completed_at if scans else None
        trend = None
        if len(scans) >= 2 and scans[1].score is not None:
            trend = round(score - scans[1].score, 1)

        # --- Data freshness ---
        freshness = self._compute_freshness(os_source, pg_events_source, pg_findings_source)

        breakdown = SeverityBreakdown(
            critical=severity_counts.get("critical", 0),
            high=severity_counts.get("high", 0),
            medium=severity_counts.get("medium", 0),
            low=severity_counts.get("low", 0),
            info=severity_counts.get("info", 0),
        )

        return SecurityScoreResponse(
            tenant_id=tenant_id,
            score=round(score, 1),
            grade=self._score_to_grade(score),
            findings_summary=breakdown,
            total_findings=total_findings,
            open_findings=open_findings,
            last_scan_at=last_scan_at,
            trend=trend,
            data_freshness=freshness,
        )

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    async def list_aggregated_findings(
        self,
        tenant_id: str,
        db: AsyncSession,
        os_client: object | None = None,
        *,
        page: int = 1,
        page_size: int = 50,
        severity: str | None = None,
        status: str | None = None,
        scanner: str | None = None,
    ) -> FindingsListResponse:
        """List findings from all 3 sources, merged and paginated."""
        all_findings: list[SecurityFindingResponse] = []

        # --- 1. PG security_findings (existing scanner data) ---
        if scanner is None or scanner == "scanner":
            pg_findings = await self._query_pg_findings(tenant_id, db, severity=severity, status=status)
            all_findings.extend(pg_findings)

        # --- 2. PG security_events → derived findings ---
        if scanner is None or scanner == "security_event":
            pg_events = await self._query_pg_events_as_findings(tenant_id, db, severity=severity)
            all_findings.extend(pg_events)

        # --- 3. OpenSearch audit-* → derived findings ---
        if (scanner is None or scanner == "audit") and os_client is not None:
            try:
                os_findings = await self._query_os_as_findings(os_client, tenant_id, severity=severity)
                all_findings.extend(os_findings)
            except Exception:
                logger.warning("OpenSearch unavailable for findings listing", exc_info=True)

        # Sort by severity priority, then by created_at desc
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        all_findings.sort(
            key=lambda f: (severity_order.get(f.severity.value, 4), -(f.created_at.timestamp() if f.created_at else 0)),
        )

        total = len(all_findings)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = all_findings[start:end]

        return FindingsListResponse(
            findings=paginated,
            total=total,
            page=page,
            page_size=page_size,
            has_more=end < total,
        )

    # ------------------------------------------------------------------
    # OpenSearch helpers
    # ------------------------------------------------------------------

    async def _query_os_severity_aggs(
        self, os_client: object, tenant_id: str
    ) -> tuple[dict[str, int], datetime | None, int]:
        """Query OpenSearch audit-* for severity aggregation counts.

        Returns (severity_counts, last_event_timestamp, total_events).
        """
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"actor.tenant_id": tenant_id}},
                        {"terms": {"severity": ["warning", "error", "critical"]}},
                    ]
                }
            },
            "size": 0,
            "aggs": {
                "severity_counts": {"terms": {"field": "severity", "size": 10}},
                "last_event": {"max": {"field": "@timestamp"}},
            },
        }

        resp = await os_client.search(index="audit*", body=body)
        hits_total = resp.get("hits", {}).get("total", {}).get("value", 0)
        aggs = resp.get("aggregations", {})

        severity_counts: dict[str, int] = {}
        for bucket in aggs.get("severity_counts", {}).get("buckets", []):
            severity_counts[bucket["key"]] = bucket["doc_count"]

        last_event_raw = aggs.get("last_event", {}).get("value_as_string")
        last_event = None
        if last_event_raw:
            with contextlib.suppress(ValueError, TypeError):
                last_event = datetime.fromisoformat(last_event_raw.replace("Z", "+00:00"))

        return severity_counts, last_event, hits_total

    async def _query_os_as_findings(
        self, os_client: object, tenant_id: str, *, severity: str | None = None
    ) -> list[SecurityFindingResponse]:
        """Query OpenSearch audit-* and convert events to SecurityFindingResponse."""
        must: list[dict] = [
            {"term": {"actor.tenant_id": tenant_id}},
            {"terms": {"severity": ["warning", "error", "critical"]}},
        ]

        # Apply severity filter (map back to OS severity)
        if severity:
            reverse_map = {v: k for k, v in _OS_SEVERITY_MAP.items()}
            os_sev = reverse_map.get(severity, severity)
            must[-1] = {"term": {"severity": os_sev}}

        body = {
            "query": {"bool": {"must": must}},
            "sort": [{"@timestamp": "desc"}],
            "size": min(_OS_MAX_FINDINGS, 200),
        }

        resp = await os_client.search(index="audit*", body=body)
        findings: list[SecurityFindingResponse] = []

        for hit in resp.get("hits", {}).get("hits", []):
            src = hit["_source"]
            os_severity = src.get("severity", "info")
            normalized_sev = _OS_SEVERITY_MAP.get(os_severity, "info")

            # Strip PII from description
            action = src.get("action", "")
            outcome = src.get("outcome", "")
            description = f"{action} — {outcome}" if outcome else action

            event_type = src.get("event_type", "unknown")
            timestamp_raw = src.get("@timestamp", datetime.now(UTC).isoformat())
            try:
                created_at = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                created_at = datetime.now(UTC)

            findings.append(
                SecurityFindingResponse(
                    id=f"derived-audit-{hit['_id']}",
                    tenant_id=tenant_id,
                    scan_id="aggregated",
                    scanner="audit",
                    severity=FindingSeverity(normalized_sev),
                    rule_id=event_type.upper().replace(".", "_"),
                    rule_name=event_type.replace(".", " ").title(),
                    resource_type=(
                        src.get("resource", {}).get("type") if isinstance(src.get("resource"), dict) else None
                    ),
                    resource_name=src.get("action", "").split(" ")[-1] if src.get("action") else None,
                    description=description,
                    status="open",
                    created_at=created_at,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # PG helpers
    # ------------------------------------------------------------------

    async def _query_pg_findings(
        self,
        tenant_id: str,
        db: AsyncSession,
        *,
        severity: str | None = None,
        status: str | None = None,
    ) -> list[SecurityFindingResponse]:
        """Query security_findings table."""
        query = select(SecurityFinding).where(SecurityFinding.tenant_id == tenant_id)
        if severity:
            query = query.where(SecurityFinding.severity == severity)
        if status:
            query = query.where(SecurityFinding.status == status)
        query = query.order_by(SecurityFinding.created_at.desc())

        result = await db.execute(query)
        return [
            SecurityFindingResponse(
                id=str(f.id),
                tenant_id=f.tenant_id,
                scan_id=str(f.scan_id),
                scanner=f.scanner,
                severity=FindingSeverity(f.severity),
                rule_id=f.rule_id,
                rule_name=f.rule_name,
                resource_type=f.resource_type,
                resource_name=f.resource_name,
                description=f.description,
                remediation=f.remediation,
                status=f.status,
                created_at=f.created_at,
                resolved_at=f.resolved_at,
            )
            for f in result.scalars().all()
        ]

    async def _query_pg_events_as_findings(
        self, tenant_id: str, db: AsyncSession, *, severity: str | None = None
    ) -> list[SecurityFindingResponse]:
        """Query security_events table and convert to findings."""
        query = select(SecurityEvent).where(SecurityEvent.tenant_id == tenant_id)
        if severity:
            reverse_map = {v: k for k, v in _OS_SEVERITY_MAP.items()}
            os_sev = reverse_map.get(severity, severity)
            query = query.where(SecurityEvent.severity == os_sev)
        query = query.order_by(SecurityEvent.created_at.desc()).limit(500)

        result = await db.execute(query)
        findings: list[SecurityFindingResponse] = []

        for evt in result.scalars().all():
            normalized_sev = _OS_SEVERITY_MAP.get(evt.severity, evt.severity)
            if normalized_sev not in ("critical", "high", "medium", "low", "info"):
                normalized_sev = "info"

            findings.append(
                SecurityFindingResponse(
                    id=f"derived-event-{evt.id}",
                    tenant_id=evt.tenant_id,
                    scan_id="aggregated",
                    scanner="security_event",
                    severity=FindingSeverity(normalized_sev),
                    rule_id=evt.event_type.upper().replace(".", "_"),
                    rule_name=evt.event_type.replace("_", " ").replace(".", " ").title(),
                    resource_type=evt.source,
                    description=f"Security event: {evt.event_type}",
                    status="open",
                    created_at=evt.created_at,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_freshness(
        os_source: DataFreshnessSource,
        pg_events_source: DataFreshnessSource,
        pg_findings_source: DataFreshnessSource,
    ) -> DataFreshness:
        """Compute data freshness status from all sources."""
        sources = {
            "opensearch_audit": os_source,
            "pg_security_events": pg_events_source,
            "pg_security_findings": pg_findings_source,
        }

        # Find most recent timestamp across all sources
        timestamps = [s.last_event_at for s in sources.values() if s.last_event_at is not None]

        if not timestamps:
            return DataFreshness(
                last_data_at=None,
                status="no_data",
                sources=sources,
            )

        last_data_at = max(timestamps)
        now = datetime.now(UTC)
        age = now - last_data_at

        if age < timedelta(hours=1):
            status = "fresh"
        elif age < timedelta(hours=24):
            status = "stale"
        else:
            status = "no_data"

        return DataFreshness(
            last_data_at=last_data_at,
            status=status,
            sources=sources,
        )

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"


# Global instance
security_aggregation_service = SecurityAggregationService()
