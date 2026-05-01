"""Tests for the Console deployment contract helpers."""

from src.repositories.gateway_deployment import _deployment_mode, _target_gateway_type, _topology


def test_console_contract_maps_self_registered_gateway_to_connect_mode():
    assert _deployment_mode("stoa", None, "self_register") == "connect"


def test_console_contract_maps_edge_mcp_gateway_to_edge_mode():
    assert _deployment_mode("stoa_edge_mcp", "edge-mcp", "argocd") == "edge"


def test_console_contract_explicit_edge_mode_wins_over_self_register_source():
    assert _deployment_mode("stoa", "edge-mcp", "self_register") == "edge"


def test_console_contract_downgrades_sidecar_without_same_pod_proof():
    assert _deployment_mode("stoa_sidecar", "sidecar", "self_register") == "connect"
    assert _topology("stoa_sidecar", "sidecar", "self_register") == "remote-agent"


def test_console_contract_keeps_sidecar_only_with_same_pod_proof():
    proof = {
        "declared_in_kubernetes": True,
        "containers": ["kong", "stoa-sidecar"],
        "target_container": "kong",
        "sidecar_container": "stoa-sidecar",
        "authz_url": "http://localhost:8081/authz",
    }
    assert (
        _deployment_mode(
            "stoa_sidecar",
            "sidecar",
            "argocd",
            deployment_mode="sidecar",
            target_gateway_type="kong",
            topology="same-pod",
            health_details={"topology_proof": proof},
        )
        == "sidecar"
    )
    assert (
        _topology(
            "stoa_sidecar",
            "sidecar",
            "argocd",
            deployment_mode="sidecar",
            target_gateway_type="kong",
            topology="same-pod",
            health_details={"topology_proof": proof},
        )
        == "same-pod"
    )


def test_console_contract_allows_same_pod_sidecar_for_supported_third_party_targets():
    proof = {
        "declared_in_kubernetes": True,
        "containers": ["apigee", "stoa-sidecar"],
        "target_container": "apigee",
        "sidecar_container": "stoa-sidecar",
        "authz_url": "http://127.0.0.1:8081/authz",
    }
    assert (
        _deployment_mode(
            "stoa_sidecar",
            "sidecar",
            "argocd",
            deployment_mode="sidecar",
            target_gateway_type="apigee",
            topology="same-pod",
            health_details={"topology_proof": proof},
        )
        == "sidecar"
    )


def test_console_contract_normalizes_stoa_target_gateway_type():
    assert _target_gateway_type("stoa_sidecar") == "stoa"


def test_console_contract_extracts_third_party_target_from_name():
    assert _target_gateway_type("stoa_sidecar", name="stoa-link-wm-staging") == "webmethods"


def test_console_contract_keeps_legacy_target_gateway_type():
    assert _target_gateway_type("webmethods") == "webmethods"
