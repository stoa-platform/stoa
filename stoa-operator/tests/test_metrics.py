"""Tests for Prometheus metrics module."""

from prometheus_client import REGISTRY
from src.metrics import (
    CP_API_DURATION,
    CP_API_REQUESTS_TOTAL,
    OPERATOR_UP,
    RECONCILIATION_DURATION,
    RECONCILIATIONS_TOTAL,
    RESOURCES_MANAGED,
    record_cp_api_call,
    record_reconciliation,
)


def test_metrics_registered():
    """All 6 metrics should be registered in the default registry."""
    names = {m.name for m in REGISTRY.collect()}
    # Counter names are registered without _total suffix in prometheus_client
    assert "stoa_operator_reconciliations" in names
    assert "stoa_operator_reconciliation_duration_seconds" in names
    assert "stoa_operator_cp_api_requests" in names
    assert "stoa_operator_cp_api_duration_seconds" in names
    assert "stoa_operator_resources_managed" in names
    assert "stoa_operator_up" in names


def test_record_reconciliation_increments_counter():
    """record_reconciliation should increment the counter and observe the histogram."""
    labels = {"kind": "gwi", "action": "create", "result": "success"}
    before = RECONCILIATIONS_TOTAL.labels(**labels)._value.get()
    record_reconciliation("gwi", "create", "success", 0.05)
    after = RECONCILIATIONS_TOTAL.labels(**labels)._value.get()
    assert after == before + 1


def test_record_reconciliation_observes_histogram():
    """record_reconciliation should add a sample to the duration histogram."""
    before = RECONCILIATION_DURATION.labels(kind="gwb", action="delete")._sum.get()
    record_reconciliation("gwb", "delete", "success", 0.123)
    after = RECONCILIATION_DURATION.labels(kind="gwb", action="delete")._sum.get()
    assert after >= before + 0.12


def test_record_cp_api_call_increments_counter():
    """record_cp_api_call should increment the counter."""
    before = CP_API_REQUESTS_TOTAL.labels(
        method="POST", endpoint="/v1/admin/gateways", status="200"
    )._value.get()
    record_cp_api_call("POST", "/v1/admin/gateways", "200", 0.01)
    after = CP_API_REQUESTS_TOTAL.labels(
        method="POST", endpoint="/v1/admin/gateways", status="200"
    )._value.get()
    assert after == before + 1


def test_record_cp_api_call_observes_histogram():
    """record_cp_api_call should add a sample to the duration histogram."""
    before = CP_API_DURATION.labels(method="GET", endpoint="/v1/admin/gateways")._sum.get()
    record_cp_api_call("GET", "/v1/admin/gateways", "200", 0.456)
    after = CP_API_DURATION.labels(method="GET", endpoint="/v1/admin/gateways")._sum.get()
    assert after >= before + 0.45


def test_operator_up_gauge():
    """OPERATOR_UP should be settable to 1 and 0."""
    OPERATOR_UP.set(1)
    assert OPERATOR_UP._value.get() == 1.0
    OPERATOR_UP.set(0)
    assert OPERATOR_UP._value.get() == 0.0


def test_resources_managed_gauge():
    """RESOURCES_MANAGED should support inc/dec per kind."""
    RESOURCES_MANAGED.labels(kind="gwi").set(0)
    RESOURCES_MANAGED.labels(kind="gwi").inc()
    RESOURCES_MANAGED.labels(kind="gwi").inc()
    assert RESOURCES_MANAGED.labels(kind="gwi")._value.get() == 2.0
    RESOURCES_MANAGED.labels(kind="gwi").dec()
    assert RESOURCES_MANAGED.labels(kind="gwi")._value.get() == 1.0


def test_record_reconciliation_error_result():
    """Error results should be tracked separately from successes."""
    before = RECONCILIATIONS_TOTAL.labels(kind="gwi", action="create", result="error")._value.get()
    record_reconciliation("gwi", "create", "error", 0.5)
    after = RECONCILIATIONS_TOTAL.labels(kind="gwi", action="create", result="error")._value.get()
    assert after == before + 1
