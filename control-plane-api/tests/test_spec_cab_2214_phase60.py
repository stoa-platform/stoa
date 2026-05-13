"""CAB-2214 red tests for the CAB-2213 Phase 6.0 guardrails contract.

These tests intentionally fail until Phase 6.1+ implements the validated plan.
They lock the API/docs side of the contract before any production reader or UI
behavior is changed.
"""

from pathlib import Path

import pytest

from src.services import gateway_metrics_service as gateway_metrics_module
from src.services.gateway_metrics_service import GatewayMetricsService

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_spec_ac4_guardrails_contract_exposes_server_state_and_freshness_fields() -> None:
    payload = GatewayMetricsService._empty_guardrails_metrics(source_healthy=True)
    required = {
        "state",
        "evaluations_count",
        "decisions_count",
        "trips_count",
        "error_count",
        "last_evaluation_delta_at",
        "last_decision_delta_at",
        "scrape_sample_at",
        "source_healthy",
        "stale_reason",
        "by_guardrail",
    }

    missing = required - set(payload)
    assert not missing, f"AC4 red: guardrails API contract missing fields: {sorted(missing)}"


def test_spec_ac6_guardrails_reader_keeps_legacy_queries_and_adds_new_counters() -> None:
    queries = "\n".join(gateway_metrics_module._GUARDRAILS_TOTAL_QUERIES.values())

    assert "stoa_guardrails_evaluations_total" in queries, "AC6 red: evaluations reader query missing"
    assert "stoa_guardrails_decisions_total" in queries, "AC6 red: decisions reader query missing"
    for legacy_metric in (
        "stoa_guardrails_pii_detected_total",
        "stoa_guardrails_injection_blocked_total",
        "stoa_guardrails_content_filtered_total",
        "stoa_prompt_guard_detected_total",
    ):
        assert legacy_metric in queries, f"AC6: legacy metric reader removed too early: {legacy_metric}"


@pytest.mark.skip(reason="TODO Phase 6.4 - cp-api reader")
def test_spec_ac8_phase66_smoke_fixtures_are_committed_and_synthetic_only() -> None:
    fixture_doc = REPO_ROOT / "docs/observability/phase-6-smoke-fixtures.md"

    assert fixture_doc.exists(), "AC8 red: synthetic Phase 6 smoke fixture doc is not committed yet"
    body = fixture_doc.read_text(encoding="utf-8")
    lower = body.lower()
    assert "guardrails-probe" in lower, "AC8 red: smoke fixtures must use the synthetic probe tenant"
    assert "synthetic" in lower, "AC8 red: smoke fixtures must be explicitly synthetic"
    assert "no real pii" in lower, "AC8 red: fixture doc must explicitly ban real PII"
    assert "no real customer prompt" in lower, "AC8 red: fixture doc must explicitly ban real customer prompts"
    for forbidden in ("4111", "4242", "john.doe@", "+33", "ssn:"):
        assert forbidden not in lower, f"AC8 red: fixture doc contains forbidden real-data marker {forbidden!r}"


@pytest.mark.skip(reason="TODO Phase 6.4 - cp-api reader")
def test_spec_ac9_legacy_metric_removal_requires_separate_plan_marker() -> None:
    removal_plan = REPO_ROOT / "docs/plans/2026-05-11-guardrails-legacy-metric-removal.md"

    assert removal_plan.exists(), "AC9 red: legacy removal must be tracked by a separate future plan"
    body = removal_plan.read_text(encoding="utf-8").lower()
    assert "separate plan" in body and "legacy" in body and "removal" in body


def test_spec_ac12_api_exposes_locked_state_precedence_helper() -> None:
    assert hasattr(
        GatewayMetricsService, "_derive_guardrails_state"
    ), "AC12 red: cp-api must own state precedence before UI can render it"

    state = GatewayMetricsService._derive_guardrails_state(  # type: ignore[attr-defined]
        source_healthy=True,
        producer_present=True,
        evaluations_count=0,
        trips_count=0,
        scrape_age_seconds=30,
        freshness_threshold_seconds=300,
    )
    assert state == "no_evaluations"


def test_spec_ac13_trips_and_errors_are_separate_counts() -> None:
    assert hasattr(
        GatewayMetricsService, "_derive_guardrails_counts"
    ), "AC13 red: cp-api must derive trips_count and error_count from decisions_total"

    counts = GatewayMetricsService._derive_guardrails_counts(  # type: ignore[attr-defined]
        {"allow": 7, "redact": 2, "block": 3, "error": 5}
    )
    assert counts["trips_count"] == 5
    assert counts["error_count"] == 5


def test_spec_ac14_per_guardrail_health_is_independent() -> None:
    threshold = GatewayMetricsService._freshness_threshold_seconds("1h")

    pii_state = GatewayMetricsService._derive_guardrails_state(
        source_healthy=True,
        producer_present=True,
        evaluations_count=1,
        trips_count=0,
        scrape_age_seconds=threshold + 1,
        freshness_threshold_seconds=threshold,
    )
    injection_state = GatewayMetricsService._derive_guardrails_state(
        source_healthy=True,
        producer_present=True,
        evaluations_count=1,
        trips_count=0,
        scrape_age_seconds=30,
        freshness_threshold_seconds=threshold,
    )
    aggregate_state = GatewayMetricsService._derive_guardrails_state(
        source_healthy=True,
        producer_present=True,
        evaluations_count=2,
        trips_count=0,
        scrape_age_seconds=30,
        freshness_threshold_seconds=threshold,
    )

    assert pii_state == "stale_data"
    assert injection_state == "evaluations_zero_trips"
    assert aggregate_state != "stale_data", "AC14 red: one stale guardrail must not flip top-level state"


@pytest.mark.skip(reason="TODO Phase 6.4 - cp-api reader")
def test_spec_ac15_prod_smoke_archive_is_safe_state_only() -> None:
    archives = sorted((REPO_ROOT / "docs/audits").glob("*phase-6-rollout*/findings.md"))

    assert archives, "AC15 red: Phase 6 rollout audit archive does not exist yet"
    body = archives[-1].read_text(encoding="utf-8")
    assert "evaluations_zero_trips" in body or "trips_observed" in body
    for forbidden_state in ("metrics_unavailable", "no_evaluations", "stale_data"):
        assert (
            f"prod:{forbidden_state}" not in body
        ), f"AC15 red: production smoke must not validate fault-injection state {forbidden_state}"


@pytest.mark.skip(reason="TODO Phase 6.4 - cp-api reader")
def test_spec_ac16_council_gate_has_machine_readable_archive() -> None:
    council_report = REPO_ROOT / "docs/audits/2026-05-11-cab-2213-council/findings.md"

    assert council_report.exists(), "AC16 red: Council report artifact is not archived in docs/audits yet"
    body = council_report.read_text(encoding="utf-8")
    assert "8.0/10" in body
    assert "go" in body.lower()


def test_spec_ac17_stale_reason_is_bounded_and_sanitized() -> None:
    payload = GatewayMetricsService._empty_guardrails_metrics(source_healthy=False)
    allowed = {"prom_unreachable", "scrape_gap", "producer_absent", "stale_unknown"}

    assert payload.get("stale_reason") in allowed, "AC17 red: stale_reason enum missing or unbounded"
    stale_reason = str(payload["stale_reason"])
    for forbidden in ("http://", "https://", "prometheus", "9090", "query=", "trace_id"):
        assert forbidden not in stale_reason.lower(), f"AC17 red: raw Prometheus detail leaked: {forbidden}"
