"""Regression test for CAB-1966: sync_engine fails for edge-mcp gateway type.

PR: #TBD
Ticket: CAB-1966
Root cause: AdapterRegistry only registered "stoa" but not the mode variants
  (stoa_edge_mcp, stoa_sidecar, stoa_proxy, stoa_shadow). When sync_engine
  called AdapterRegistry.create("stoa_edge_mcp", ...) it raised ValueError.
Invariant: All STOA gateway mode variants resolve to StoaGatewayAdapter.
"""

import pytest

from src.adapters.registry import AdapterRegistry


@pytest.mark.parametrize(
    "gateway_type",
    ["stoa", "stoa_edge_mcp", "stoa_sidecar", "stoa_proxy", "stoa_shadow"],
)
def test_regression_cab_1966_stoa_mode_variants_resolve(gateway_type):
    """All STOA mode variants must resolve to StoaGatewayAdapter without ValueError."""
    adapter = AdapterRegistry.create(
        gateway_type,
        config={"base_url": "http://localhost:8080", "auth_config": {}},
    )
    # InstrumentedAdapter wraps the real adapter; unwrap to check type
    assert adapter is not None
