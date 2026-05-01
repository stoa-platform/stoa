from __future__ import annotations

from src.services.catalog_api_definition import (
    extract_deployment_targets,
    extract_target_gateway_names,
    normalize_api_definition,
)


def test_normalize_kubernetes_style_api_preserves_deployment_targets() -> None:
    raw = {
        "apiVersion": "stoa.cab-i.com/v1",
        "kind": "API",
        "metadata": {"name": "control-plane-api", "version": "2.0"},
        "spec": {
            "displayName": "Control Plane API",
            "backend": {"url": "https://api.gostoa.dev"},
            "status": "published",
            "tags": ["internal"],
            "deployments": {
                "dev": {"gateways": ["connect-webmethods-dev"]},
                "prod": {"gateway": "connect-webmethods"},
            },
            "gateways": [{"instance": "stoa-prod", "environment": "prod"}],
            "gateway": {"type": "REST"},
        },
    }

    normalized = normalize_api_definition(raw)

    assert normalized["name"] == "control-plane-api"
    assert normalized["backend_url"] == "https://api.gostoa.dev"
    assert normalized["deployments"]["dev"]["gateways"] == ["connect-webmethods-dev"]
    assert normalized["gateways"] == [{"instance": "stoa-prod", "environment": "prod"}]
    assert "gateway" not in normalized


def test_extract_targets_from_gateways_list_and_name_map() -> None:
    api = {
        "name": "payments",
        "gateways": [
            {"instance": "connect-webmethods-dev", "environment": "dev"},
            "stoa-prod",
        ],
    }

    targets = extract_deployment_targets(api)

    assert [(t.instance, t.environment, t.activated) for t in targets] == [
        ("connect-webmethods-dev", "dev", True),
        ("stoa-prod", None, True),
    ]
    assert extract_target_gateway_names(api) == ["connect-webmethods-dev", "stoa-prod"]


def test_extract_targets_from_deployments_gateway_shapes() -> None:
    api = {
        "name": "payments",
        "deployments": {
            "dev": {
                "gateways": [
                    {"instance": "connect-webmethods-dev", "activated": False},
                    "stoa-dev",
                ]
            },
            "prod": {"gateway": "connect-webmethods"},
            "staging": False,
        },
    }

    targets = extract_deployment_targets(api)

    assert [(t.instance, t.environment, t.activated, t.source) for t in targets] == [
        ("connect-webmethods-dev", "dev", False, "deployments"),
        ("stoa-dev", "dev", True, "deployments"),
        ("connect-webmethods", "production", True, "deployments"),
    ]


def test_parent_deployment_activation_applies_to_nested_gateways() -> None:
    api = {
        "name": "payments",
        "deployments": {
            "dev": {
                "activated": False,
                "gateways": ["connect-webmethods-dev"],
            }
        },
    }

    targets = extract_deployment_targets(api)

    assert [(t.instance, t.environment, t.activated) for t in targets] == [
        ("connect-webmethods-dev", "dev", False)
    ]


def test_boolean_deployments_are_environment_markers_not_gateway_names() -> None:
    api = {"name": "payments", "deployments": {"dev": True, "staging": False}}

    targets = extract_deployment_targets(api)

    assert [(t.instance, t.environment) for t in targets] == [(None, "dev")]
    assert extract_target_gateway_names(api) == []
