"""Regression test for CAB-1819: connect mode must not fall through to edge-mcp.

PR: #1741
Ticket: CAB-1819
Root cause: _normalize_mode() had no "connect" entry in mode_map, causing all
  stoa-connect agents to silently register with mode="edge-mcp" instead of "connect".
Invariant: connect mode is preserved as-is through both normalization functions.
"""


def test_regression_cab_1819_connect_mode_not_fallthrough():
    """_normalize_mode("connect") must return "connect", not "edge-mcp"."""
    from src.models.gateway_instance import GatewayType
    from src.routers.gateway_internal import _mode_to_gateway_type, _normalize_mode

    # connect must be preserved as-is, not mapped to edge-mcp
    assert _normalize_mode("connect") == "connect"
    assert _normalize_mode("connect") != "edge-mcp"

    # connect maps to GatewayType.STOA (bridge agent, not a new adapter type)
    assert _mode_to_gateway_type("connect") == GatewayType.STOA
