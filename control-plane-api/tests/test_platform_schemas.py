"""Tests for platform status schemas (CAB-1291)"""
from datetime import datetime

import pytest

from src.schemas.platform import (
    ComponentHealthEnum,
    ComponentStatus,
    ExternalLink,
    GitOpsAppStatus,
    GitOpsDiffResource,
    GitOpsDiffResponse,
    GitOpsHealthStatusEnum,
    GitOpsSummary,
    GitOpsSyncRequest,
    GitOpsSyncResponse,
    GitOpsSyncStatusEnum,
    PlatformEvent,
    PlatformEventSeverityEnum,
    PlatformEventTypeEnum,
    PlatformStatusResponse,
)


class TestEnums:
    def test_component_health_values(self):
        assert ComponentHealthEnum.HEALTHY == "healthy"
        assert ComponentHealthEnum.DEGRADED == "degraded"
        assert ComponentHealthEnum.UNHEALTHY == "unhealthy"
        assert ComponentHealthEnum.UNKNOWN == "unknown"

    def test_sync_status_values(self):
        assert GitOpsSyncStatusEnum.SYNCED == "Synced"
        assert GitOpsSyncStatusEnum.OUT_OF_SYNC == "OutOfSync"

    def test_health_status_values(self):
        assert GitOpsHealthStatusEnum.HEALTHY == "Healthy"
        assert GitOpsHealthStatusEnum.PROGRESSING == "Progressing"

    def test_event_type_values(self):
        assert PlatformEventTypeEnum.SYNC_STARTED == "sync_started"
        assert PlatformEventTypeEnum.DRIFT_DETECTED == "drift_detected"

    def test_event_severity_values(self):
        assert PlatformEventSeverityEnum.INFO == "info"
        assert PlatformEventSeverityEnum.ERROR == "error"


class TestComponentStatus:
    def test_required_fields(self):
        cs = ComponentStatus(
            name="api", status=ComponentHealthEnum.HEALTHY,
            last_check=datetime(2026, 1, 1),
        )
        assert cs.name == "api"
        assert cs.message is None
        assert cs.external_url is None

    def test_all_fields(self):
        cs = ComponentStatus(
            name="gw", status=ComponentHealthEnum.DEGRADED,
            last_check=datetime(2026, 1, 1),
            message="High latency", external_url="https://gw.example.com",
        )
        assert cs.message == "High latency"


class TestGitOpsModels:
    def test_app_status_minimal(self):
        app = GitOpsAppStatus(
            name="stoa-gateway", sync_status="Synced", health_status="Healthy",
        )
        assert app.display_name is None
        assert app.revision is None

    def test_summary_defaults(self):
        summary = GitOpsSummary(
            total_apps=3, synced_count=2, out_of_sync_count=1,
            healthy_count=2, degraded_count=1, argocd_url="https://argocd.example.com",
        )
        assert summary.apps == []

    def test_diff_resource(self):
        res = GitOpsDiffResource(
            name="deploy-api", kind="Deployment", status="OutOfSync",
        )
        assert res.namespace is None
        assert res.diff is None

    def test_diff_response_defaults(self):
        resp = GitOpsDiffResponse(
            application="stoa-gw", total_resources=5, diff_count=1,
        )
        assert resp.resources == []


class TestPlatformStatusResponse:
    def test_timestamp_auto(self):
        gitops = GitOpsSummary(
            total_apps=0, synced_count=0, out_of_sync_count=0,
            healthy_count=0, degraded_count=0, argocd_url="https://argocd",
        )
        resp = PlatformStatusResponse(
            components=[], gitops=gitops, external_links={},
        )
        assert isinstance(resp.timestamp, datetime)
        assert resp.recent_events == []


class TestSyncModels:
    def test_sync_request_defaults(self):
        req = GitOpsSyncRequest()
        assert req.prune is False
        assert req.revision is None

    def test_sync_response(self):
        resp = GitOpsSyncResponse(
            status="triggered", application="stoa-gw",
        )
        assert resp.message is None


class TestOtherModels:
    def test_platform_event(self):
        evt = PlatformEvent(
            timestamp=datetime(2026, 1, 1), type="sync_started",
            severity="info", application="api", message="Sync started",
        )
        assert evt.details is None

    def test_external_link(self):
        link = ExternalLink(name="Grafana", url="https://grafana.example.com")
        assert link.icon is None
