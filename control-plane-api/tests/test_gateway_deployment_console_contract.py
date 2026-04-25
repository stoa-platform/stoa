"""Tests for the Console deployment contract helpers."""

from src.repositories.gateway_deployment import _deployment_mode, _target_gateway_type


def test_console_contract_maps_self_registered_gateway_to_connect_mode():
    assert _deployment_mode("stoa", None, "self_register") == "connect"


def test_console_contract_maps_edge_mcp_gateway_to_edge_mode():
    assert _deployment_mode("stoa_edge_mcp", "edge-mcp", "argocd") == "edge"


def test_console_contract_explicit_edge_mode_wins_over_self_register_source():
    assert _deployment_mode("stoa", "edge-mcp", "self_register") == "edge"


def test_console_contract_keeps_sidecar_only_for_explicit_sidecar_mode():
    assert _deployment_mode("stoa_sidecar", "sidecar", "self_register") == "sidecar"


def test_console_contract_normalizes_stoa_target_gateway_type():
    assert _target_gateway_type("stoa_sidecar") == "stoa"


def test_console_contract_keeps_legacy_target_gateway_type():
    assert _target_gateway_type("webmethods") == "webmethods"
