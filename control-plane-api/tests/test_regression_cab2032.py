"""Regression tests for CAB-2032: Cleanup metrics |default tenant leak.

Verifies that _build_labels() uses exact tenant match, not regex with |default fallback.
"""

from src.services.prometheus_client import PrometheusClient


def test_regression_cab2032_no_default_fallback_in_labels():
    """_build_labels MUST NOT include |default — exact tenant match only."""
    client = PrometheusClient.__new__(PrometheusClient)
    labels = client._build_labels(tenant_id="acme")

    # Must be exact match, no regex
    assert labels == 'tenant="acme"'
    assert "|default" not in labels
    assert "=~" not in labels


def test_regression_cab2032_no_tenant_no_label():
    """_build_labels with no tenant_id produces no tenant label."""
    client = PrometheusClient.__new__(PrometheusClient)
    labels = client._build_labels()
    assert "tenant" not in labels


def test_regression_cab2032_subscription_and_tenant():
    """_build_labels with both subscription_id and tenant_id produces both labels."""
    client = PrometheusClient.__new__(PrometheusClient)
    labels = client._build_labels(subscription_id="sub-1", tenant_id="acme")
    assert 'subscription_id="sub-1"' in labels
    assert 'tenant="acme"' in labels
    assert "|default" not in labels
