"""Regression coverage for staging webMethods target URL isolation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING_OVERLAY = REPO_ROOT / "k8s" / "gateways" / "overlays" / "staging"
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


def _env_map_from_stoa_link_patch() -> dict[str, str]:
    kustomization = _load_yaml(STAGING_OVERLAY / "kustomization.yaml")[0]
    link_patch = next(
        patch
        for patch in kustomization["patches"]
        if patch["target"]["kind"] == "Deployment" and patch["target"]["name"] == "stoa-link-wm"
    )
    deployment = yaml.safe_load(link_patch["patch"])
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    return {item["name"]: item["value"] for item in env}


def test_regression_cab_2240_staging_link_targets_real_webmethods_gateway() -> None:
    env = _env_map_from_stoa_link_patch()

    assert env["STOA_GATEWAY_PUBLIC_URL"] == "https://staging-wm-k3s.gostoa.dev"
    assert env["STOA_TARGET_GATEWAY_URL"] == "https://staging-wm.gostoa.dev"


def test_regression_cab_2240_gateway_instances_keep_runtime_and_target_urls_separate() -> None:
    instances = {doc["metadata"]["name"]: doc for doc in _load_yaml(STAGING_OVERLAY / "gateway-instances.yaml")}

    connect_endpoints = instances["connect-webmethods-staging"]["spec"]["endpoints"]
    assert connect_endpoints["publicUrl"] == "https://staging-wm.gostoa.dev"
    assert connect_endpoints["targetGatewayUrl"] == "https://staging-wm.gostoa.dev"

    link_endpoints = instances["stoa-link-wm-staging"]["spec"]["endpoints"]
    assert link_endpoints["publicUrl"] == "https://staging-wm-k3s.gostoa.dev"
    assert link_endpoints["targetGatewayUrl"] == "https://staging-wm.gostoa.dev"


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
