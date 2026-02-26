"""Security Scanner Service — score engine + drift detection (CAB-1461 P1).

Provides:
- Security score calculation (0-100) per tenant
- Findings storage and query (PostgreSQL)
- Golden state drift detection
- Compliance mapping (DORA, NIS2)
- Secrets health tracking
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.security_finding import SecurityBaseline, SecurityFinding, SecurityScan
from ..schemas.security_posture import (
    ComplianceControl,
    ComplianceScoreResponse,
    DriftAlert,
    DriftReportResponse,
    FindingSeverity,
    FindingsListResponse,
    ScanHistoryResponse,
    SecretsHealthResponse,
    SecurityFindingResponse,
    SecurityScanResponse,
    SecurityScoreResponse,
    SeverityBreakdown,
)

logger = logging.getLogger(__name__)

# Severity weights for score calculation
_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 5.0,
    "medium": 2.0,
    "low": 0.5,
    "info": 0.0,
}

# DORA compliance controls (Art.5, Art.9, Art.11)
_DORA_CONTROLS: list[dict[str, str]] = [
    {"control_id": "DORA-5.1", "article": "Art.5", "description": "ICT risk management framework"},
    {"control_id": "DORA-5.2", "article": "Art.5", "description": "ICT asset classification"},
    {"control_id": "DORA-9.1", "article": "Art.9", "description": "Protection and prevention measures"},
    {"control_id": "DORA-9.2", "article": "Art.9", "description": "Encryption and cryptographic controls"},
    {"control_id": "DORA-9.3", "article": "Art.9", "description": "Network security management"},
    {"control_id": "DORA-11.1", "article": "Art.11", "description": "ICT response and recovery plans"},
    {"control_id": "DORA-11.2", "article": "Art.11", "description": "Backup policies and procedures"},
]

# NIS2 compliance controls
_NIS2_CONTROLS: list[dict[str, str]] = [
    {"control_id": "NIS2-21.1", "article": "Art.21", "description": "Risk analysis and security policies"},
    {"control_id": "NIS2-21.2", "article": "Art.21", "description": "Incident handling"},
    {"control_id": "NIS2-21.3", "article": "Art.21", "description": "Business continuity and crisis management"},
    {"control_id": "NIS2-21.4", "article": "Art.21", "description": "Supply chain security"},
    {"control_id": "NIS2-21.5", "article": "Art.21", "description": "Vulnerability handling and disclosure"},
    {"control_id": "NIS2-23.1", "article": "Art.23", "description": "Incident notification obligations"},
]


class SecurityScannerService:
    """Orchestrates security scanning, scoring, and compliance."""

    # --- Score Calculation ---

    async def calculate_score(self, tenant_id: str, db: AsyncSession) -> SecurityScoreResponse:
        """Calculate security score (0-100) for a tenant.

        Score = max(0, 100 - weighted_penalty)
        Where weighted_penalty = sum(severity_weight * count_per_severity)
        """
        # Count open findings by severity
        result = await db.execute(
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
        severity_counts: dict[str, int] = {}
        total_open = 0
        for row in result.all():
            severity_counts[row.severity] = row.cnt
            total_open += row.cnt

        # Calculate weighted penalty
        penalty = sum(_SEVERITY_WEIGHTS.get(sev, 0) * count for sev, count in severity_counts.items())
        score = max(0.0, 100.0 - penalty)

        # Total findings (all statuses)
        total_result = await db.execute(
            select(func.count(SecurityFinding.id)).where(SecurityFinding.tenant_id == tenant_id)
        )
        total_findings = total_result.scalar_one()

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
            open_findings=total_open,
            last_scan_at=last_scan_at,
            trend=trend,
        )

    # --- Findings CRUD ---

    async def list_findings(
        self,
        tenant_id: str,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 50,
        severity: str | None = None,
        status: str | None = None,
        scanner: str | None = None,
    ) -> FindingsListResponse:
        """List findings for a tenant with optional filters."""
        query = select(SecurityFinding).where(SecurityFinding.tenant_id == tenant_id)

        if severity:
            query = query.where(SecurityFinding.severity == severity)
        if status:
            query = query.where(SecurityFinding.status == status)
        if scanner:
            query = query.where(SecurityFinding.scanner == scanner)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        # Paginate
        query = query.order_by(
            case(
                (SecurityFinding.severity == "critical", 0),
                (SecurityFinding.severity == "high", 1),
                (SecurityFinding.severity == "medium", 2),
                (SecurityFinding.severity == "low", 3),
                else_=4,
            ),
            SecurityFinding.created_at.desc(),
        )
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        findings = [
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

        return FindingsListResponse(
            findings=findings,
            total=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        )

    async def ingest_findings(
        self,
        tenant_id: str,
        scan_id: str,
        scanner: str,
        raw_findings: list[dict],
        db: AsyncSession,
    ) -> int:
        """Ingest raw findings from a scanner, return count ingested."""
        count = 0
        for raw in raw_findings:
            finding = SecurityFinding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                scan_id=uuid.UUID(scan_id),
                scanner=scanner,
                severity=raw.get("severity", "info").lower(),
                rule_id=raw.get("rule_id", raw.get("id", "unknown")),
                title=raw.get("rule_name", raw.get("title", "Unknown rule")),
                resource_type=raw.get("resource_type"),
                resource_name=raw.get("resource_name", raw.get("resource")),
                description=raw.get("description"),
                remediation=raw.get("remediation"),
                details=raw,
                status="open",
            )
            db.add(finding)
            count += 1

        # Update scan record
        await db.execute(
            update(SecurityScan)
            .where(SecurityScan.id == uuid.UUID(scan_id))
            .values(
                findings_count=count,
                status="completed",
                completed_at=datetime.now(UTC),
            )
        )

        await db.flush()
        return count

    async def resolve_finding(self, finding_id: str, db: AsyncSession) -> bool:
        """Mark a finding as resolved."""
        result = await db.execute(
            update(SecurityFinding)
            .where(SecurityFinding.id == uuid.UUID(finding_id))
            .values(status="resolved", resolved_at=datetime.now(UTC))
        )
        return result.rowcount > 0

    # --- Scan Management ---

    async def create_scan(self, tenant_id: str, scanner: str, db: AsyncSession) -> str:
        """Create a new scan record, return scan_id."""
        scan = SecurityScan(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            scanner=scanner,
            status="running",
        )
        db.add(scan)
        await db.flush()
        return str(scan.id)

    async def complete_scan(self, scan_id: str, score: float, db: AsyncSession) -> None:
        """Mark a scan as completed with its score."""
        await db.execute(
            update(SecurityScan)
            .where(SecurityScan.id == uuid.UUID(scan_id))
            .values(status="completed", score=score, completed_at=datetime.now(UTC))
        )

    async def get_scan_history(self, tenant_id: str, db: AsyncSession, *, limit: int = 20) -> ScanHistoryResponse:
        """Get recent scan history for a tenant."""
        result = await db.execute(
            select(SecurityScan)
            .where(SecurityScan.tenant_id == tenant_id)
            .order_by(SecurityScan.started_at.desc())
            .limit(limit)
        )
        scans = [
            SecurityScanResponse(
                id=str(s.id),
                tenant_id=s.tenant_id,
                scanner=s.scanner,
                status=s.status,
                findings_count=s.findings_count,
                score=s.score,
                started_at=s.started_at,
                completed_at=s.completed_at,
            )
            for s in result.scalars().all()
        ]
        count_result = await db.execute(select(func.count(SecurityScan.id)).where(SecurityScan.tenant_id == tenant_id))
        return ScanHistoryResponse(scans=scans, total=count_result.scalar_one())

    # --- Drift Detection ---

    async def set_baseline(self, tenant_id: str, baseline: dict, db: AsyncSession) -> None:
        """Set or update golden state baseline for a tenant."""
        existing = await db.execute(select(SecurityBaseline).where(SecurityBaseline.tenant_id == tenant_id))
        row = existing.scalar_one_or_none()
        if row:
            row.baseline = baseline
            row.updated_at = datetime.now(UTC)
        else:
            db.add(
                SecurityBaseline(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    baseline=baseline,
                )
            )
        await db.flush()

    async def detect_drift(self, tenant_id: str, db: AsyncSession) -> DriftReportResponse:
        """Compare current findings against golden state baseline."""
        # Load baseline
        result = await db.execute(select(SecurityBaseline).where(SecurityBaseline.tenant_id == tenant_id))
        baseline_row = result.scalar_one_or_none()
        if not baseline_row:
            return DriftReportResponse(
                tenant_id=tenant_id,
                baseline_date=None,
                drifts=[],
                total_drifts=0,
                has_baseline=False,
            )

        baseline: dict = baseline_row.baseline

        # Get current open findings indexed by rule_id
        findings_result = await db.execute(
            select(SecurityFinding.rule_id, SecurityFinding.title, SecurityFinding.severity)
            .where(
                SecurityFinding.tenant_id == tenant_id,
                SecurityFinding.status == "open",
            )
            .distinct(SecurityFinding.rule_id)
        )
        current_rules = {row.rule_id: row for row in findings_result.all()}

        drifts: list[DriftAlert] = []
        now = datetime.now(UTC)

        for rule_id, expected_status in baseline.items():
            actual = current_rules.get(rule_id)
            if expected_status == "resolved" and actual is not None:
                # Regression: was resolved, now open again
                drifts.append(
                    DriftAlert(
                        rule_id=rule_id,
                        rule_name=actual.title,
                        expected_status=expected_status,
                        actual_status="open",
                        severity=FindingSeverity(actual.severity),
                        detected_at=now,
                    )
                )

        return DriftReportResponse(
            tenant_id=tenant_id,
            baseline_date=baseline_row.updated_at or baseline_row.created_at,
            drifts=drifts,
            total_drifts=len(drifts),
            has_baseline=True,
        )

    # --- Compliance Mapping ---

    async def get_compliance_score(self, tenant_id: str, framework: str, db: AsyncSession) -> ComplianceScoreResponse:
        """Calculate compliance score for a given framework."""
        controls_def = _DORA_CONTROLS if framework.upper() == "DORA" else _NIS2_CONTROLS

        # Count open findings by severity for the tenant
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
        severity_map = {row.severity: row.cnt for row in findings_result.all()}
        critical_count = severity_map.get("critical", 0)
        high_count = severity_map.get("high", 0)

        controls: list[ComplianceControl] = []
        compliant_count = 0

        for ctrl in controls_def:
            # Simple heuristic: critical/high findings -> non-compliant for related controls
            if critical_count > 0:
                status = "non_compliant"
            elif high_count > 0:
                status = "partial"
            else:
                status = "compliant"
                compliant_count += 1

            controls.append(
                ComplianceControl(
                    control_id=ctrl["control_id"],
                    framework=framework.upper(),
                    article=ctrl["article"],
                    description=ctrl["description"],
                    status=status,
                    findings_count=critical_count + high_count,
                )
            )

        total = len(controls)
        score = (compliant_count / total * 100) if total > 0 else 0.0

        return ComplianceScoreResponse(
            tenant_id=tenant_id,
            framework=framework.upper(),
            score=round(score, 1),
            controls=controls,
            compliant_count=compliant_count,
            total_controls=total,
        )

    # --- Secrets Health ---

    async def get_secrets_health(self, tenant_id: str) -> SecretsHealthResponse:
        """Check secrets health via Infisical API.

        Returns a static response when Infisical is unavailable (graceful degradation).
        """
        # Graceful degradation: return empty response if Infisical is not configured
        # In production, this would call the Infisical API
        logger.info(f"Secrets health check for tenant {tenant_id} (Infisical integration pending)")
        return SecretsHealthResponse(
            tenant_id=tenant_id,
            total_secrets=0,
            healthy=0,
            expiring_soon=0,
            expired=0,
            orphan=0,
            secrets=[],
        )

    # --- Helpers ---

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
security_scanner_service = SecurityScannerService()
