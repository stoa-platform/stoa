"""Regression coverage for webMethods URL isolation across environments."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_OVERLAY = REPO_ROOT / "k8s" / "gateways" / "overlays" / "dev"
STAGING_OVERLAY = REPO_ROOT / "k8s" / "gateways" / "overlays" / "staging"
PROD_OVERLAY = REPO_ROOT / "k8s" / "gateways" / "overlays" / "production"
GATEWAY_INSTANCE_CRD = REPO_ROOT / "charts" / "stoa-platform" / "crds" / "gatewayinstances.gostoa.dev.yaml"
MIGRATION = (
    REPO_ROOT
    / "control-plane-api"
    / "alembic"
    / "versions"
    / "105_fix_webmethods_staging_target_urls.py"
)


def _load_yaml(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [doc for doc in yaml.safe_load_all(handle) if isinstance(doc, dict)]


def _env_map_from_stoa_link_patch(overlay: Path) -> dict[str, str]:
    kustomization = _load_yaml(overlay / "kustomization.yaml")[0]
    link_patch = next(
        patch
        for patch in kustomization["patches"]
        if patch["target"]["kind"] == "Deployment" and patch["target"]["name"] == "stoa-link-wm"
    )
    deployment = yaml.safe_load(link_patch["patch"])
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    return {item["name"]: item["value"] for item in env}


def test_regression_cab_2240_staging_link_targets_real_webmethods_gateway() -> None:
    env = _env_map_from_stoa_link_patch(STAGING_OVERLAY)

    assert env["STOA_GATEWAY_PUBLIC_URL"] == "https://staging-wm-k3s.gostoa.dev"
    assert env["STOA_TARGET_GATEWAY_URL"] == "https://staging-wm.gostoa.dev"
    assert env["STOA_GATEWAY_UI_URL"] == "https://staging-wm-ui.gostoa.dev/apigatewayui/"


def test_regression_cab_2240_link_registration_urls_are_explicit_for_all_envs() -> None:
    expected = {
        DEV_OVERLAY: {
            "STOA_GATEWAY_PUBLIC_URL": "https://dev-wm-k3s.gostoa.dev",
            "STOA_TARGET_GATEWAY_URL": "https://dev-wm.gostoa.dev",
            "STOA_GATEWAY_UI_URL": "https://dev-wm-ui.gostoa.dev/apigatewayui/",
        },
        STAGING_OVERLAY: {
            "STOA_GATEWAY_PUBLIC_URL": "https://staging-wm-k3s.gostoa.dev",
            "STOA_TARGET_GATEWAY_URL": "https://staging-wm.gostoa.dev",
            "STOA_GATEWAY_UI_URL": "https://staging-wm-ui.gostoa.dev/apigatewayui/",
        },
        PROD_OVERLAY: {
            "STOA_GATEWAY_PUBLIC_URL": "https://vps-wm-link.gostoa.dev",
            "STOA_TARGET_GATEWAY_URL": "https://vps-wm.gostoa.dev",
            "STOA_GATEWAY_UI_URL": "https://vps-wm-ui.gostoa.dev/apigatewayui/",
        },
    }

    for overlay, urls in expected.items():
        env = _env_map_from_stoa_link_patch(overlay)
        for key, value in urls.items():
            assert env[key] == value


def test_regression_cab_2240_gateway_instances_keep_runtime_and_target_urls_separate() -> None:
    instances = {doc["metadata"]["name"]: doc for doc in _load_yaml(STAGING_OVERLAY / "gateway-instances.yaml")}

    connect_endpoints = instances["connect-webmethods-staging"]["spec"]["endpoints"]
    assert connect_endpoints["publicUrl"] == "https://staging-wm.gostoa.dev"
    assert connect_endpoints["targetGatewayUrl"] == "https://staging-wm.gostoa.dev"
    assert connect_endpoints["uiUrl"] == "https://staging-wm-ui.gostoa.dev/apigatewayui/"

    link_endpoints = instances["stoa-link-wm-staging"]["spec"]["endpoints"]
    assert link_endpoints["publicUrl"] == "https://staging-wm-k3s.gostoa.dev"
    assert link_endpoints["targetGatewayUrl"] == "https://staging-wm.gostoa.dev"
    assert link_endpoints["uiUrl"] == "https://staging-wm-ui.gostoa.dev/apigatewayui/"


def test_regression_cab_2240_gateway_instances_expose_webmethods_ui_urls_for_all_envs() -> None:
    cases = (
        (
            DEV_OVERLAY,
            "connect-webmethods-dev",
            "https://dev-wm.gostoa.dev",
            "https://dev-wm.gostoa.dev",
            "https://dev-wm-ui.gostoa.dev/apigatewayui/",
        ),
        (
            DEV_OVERLAY,
            "stoa-link-wm-dev",
            "https://dev-wm-k3s.gostoa.dev",
            "https://dev-wm.gostoa.dev",
            "https://dev-wm-ui.gostoa.dev/apigatewayui/",
        ),
        (
            STAGING_OVERLAY,
            "connect-webmethods-staging",
            "https://staging-wm.gostoa.dev",
            "https://staging-wm.gostoa.dev",
            "https://staging-wm-ui.gostoa.dev/apigatewayui/",
        ),
        (
            STAGING_OVERLAY,
            "stoa-link-wm-staging",
            "https://staging-wm-k3s.gostoa.dev",
            "https://staging-wm.gostoa.dev",
            "https://staging-wm-ui.gostoa.dev/apigatewayui/",
        ),
        (
            PROD_OVERLAY,
            "connect-webmethods-prod",
            "https://vps-wm.gostoa.dev",
            "https://vps-wm.gostoa.dev",
            "https://vps-wm-ui.gostoa.dev/apigatewayui/",
        ),
        (
            PROD_OVERLAY,
            "vps-wm-link-prod",
            "https://vps-wm-link.gostoa.dev",
            "https://vps-wm.gostoa.dev",
            "https://vps-wm-ui.gostoa.dev/apigatewayui/",
        ),
    )

    for overlay, name, public_url, target_gateway_url, ui_url in cases:
        instances = {doc["metadata"]["name"]: doc for doc in _load_yaml(overlay / "gateway-instances.yaml")}
        endpoints = instances[name]["spec"]["endpoints"]
        assert endpoints["publicUrl"] == public_url
        assert endpoints["targetGatewayUrl"] == target_gateway_url
        assert endpoints["uiUrl"] == ui_url


def test_regression_cab_2240_crd_declares_gateway_url_contract() -> None:
    crd = _load_yaml(GATEWAY_INSTANCE_CRD)[0]
    schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
    endpoints = schema["properties"]["spec"]["properties"]["endpoints"]["properties"]

    assert endpoints["publicUrl"]["description"].startswith("User or tenant reachable runtime URL")
    assert "Third-party gateway" in endpoints["targetGatewayUrl"]["description"]
    assert "never use the STOA Link runtime URL" in endpoints["uiUrl"]["description"]


def test_regression_cab_2240_migration_repairs_all_staging_webmethods_rows() -> None:
    spec = importlib.util.spec_from_file_location("migration_105", MIGRATION)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fixes = {
        name: (public_url, target_gateway_url)
        for name, _environment, public_url, target_gateway_url in module._WEBMETHODS_STAGING_URL_FIXES
    }

    assert fixes["connect-webmethods-staging"] == (
        "https://staging-wm.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    )
    assert fixes["connect-webmethods-staging-connect-staging"] == (
        "https://staging-wm.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    )
    assert fixes["stoa-link-wm-staging"] == (
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    )
    assert fixes["stoa-link-wm-staging-sidecar-staging"] == (
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    )
