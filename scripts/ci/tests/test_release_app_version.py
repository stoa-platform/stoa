"""Resolve component image versions from release tags or version files."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "release_app_version.py"

# Import the helpers directly so the assertions stay close to the contract.
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import release_app_version as rav  # noqa: E402


def test_version_from_component_tags():
    assert rav.version_from_tag("portal-v1.4.0", "portal") == "1.4.0"
    assert rav.version_from_tag("control-plane-ui-v1.13.0", "control-plane-ui") == "1.13.0"
    assert rav.version_from_tag("control-plane-api-v1.15.0", "control-plane-api") == "1.15.0"
    assert rav.version_from_tag("stoa-gateway-v0.9.27", "stoa-gateway") == "0.9.27"


def test_version_from_tag_rejects_mismatched_or_invalid_tags():
    assert rav.version_from_tag("control-plane-ui-v1.13.0", "portal") is None
    assert rav.version_from_tag("portal-v1.4.0", "control-plane-api") is None
    assert rav.version_from_tag("v1.4.0", "portal") is None
    assert rav.version_from_tag("portal-v", "portal") is None
    assert rav.version_from_tag("main", "portal") is None
    assert rav.version_from_tag("portal-vnot-a-version", "portal") is None


def test_version_from_source_reads_checked_out_files():
    assert rav.version_from_source(ROOT, "portal") == json.loads(
        (ROOT / "portal" / "package.json").read_text()
    )["version"]
    assert rav.version_from_source(ROOT, "control-plane-ui") == json.loads(
        (ROOT / "control-plane-ui" / "package.json").read_text()
    )["version"]
    # Import tomllib here to keep the test aligned with the production parser.
    import tomllib

    expected = tomllib.loads(
        (ROOT / "control-plane-api" / "pyproject.toml").read_text()
    )["project"]["version"]
    assert rav.version_from_source(ROOT, "control-plane-api") == expected


def test_resolve_prefers_matching_tag_over_version_file():
    version, verify = rav.resolve_app_version("portal", "portal-v9.9.9", ROOT, event_name="release")
    assert version == "9.9.9"
    assert verify is True


def test_resolve_falls_back_to_version_file_when_tag_is_not_component_scoped():
    version, verify = rav.resolve_app_version("portal", "main", ROOT, event_name="workflow_dispatch")
    assert version == rav.version_from_source(ROOT, "portal")
    assert verify is True


def test_resolve_skips_unversioned_services():
    assert rav.resolve_app_version("keycloak", "keycloak-v1.0.0", ROOT) == ("", False)
    assert rav.resolve_app_version("stoa-gateway", "stoa-gateway-v0.9.27", ROOT) == ("", False)


def test_build_args_only_for_versioned_services():
    assert rav.build_args_for("portal", "1.4.0") == (
        "APP_VERSION=1.4.0\nVITE_APP_VERSION=1.4.0\n"
    )
    assert rav.build_args_for("control-plane-api", "1.15.0") == "APP_VERSION=1.15.0\n"
    assert rav.build_args_for("keycloak", "1.0.0") == ""


def test_cli_writes_github_output(tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            "portal",
            "--tag",
            "portal-v1.4.0",
            "--event-name",
            "release",
            "--repo-root",
            str(ROOT),
        ],
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text()
    assert "version=1.4.0\n" in text
    assert "verify=true\n" in text
    assert "APP_VERSION=1.4.0" in text
    assert "VITE_APP_VERSION=1.4.0" in text


def test_cli_errors_when_fallback_file_is_missing(tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            "portal",
            "--tag",
            "main",
            "--repo-root",
            str(tmp_path),
        ],
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "::error::Failed to resolve application version:" in result.stderr
    assert not output.exists()

def test_resolve_ignores_tag_shaped_dispatch_ref():
    version, verify = rav.resolve_app_version(
        "portal", "portal-v9.9.9", ROOT, event_name="workflow_dispatch"
    )
    assert version == rav.version_from_source(ROOT, "portal")
    assert version != "9.9.9"
    assert verify is True


def test_resolve_ignores_tag_when_event_name_is_missing():
    version, verify = rav.resolve_app_version("portal", "portal-v9.9.9", ROOT)
    assert version == rav.version_from_source(ROOT, "portal")
    assert verify is True

def test_cli_dispatch_ignores_tag_shaped_ref(tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            "portal",
            "--tag",
            "portal-v9.9.9",
            "--event-name",
            "workflow_dispatch",
            "--repo-root",
            str(ROOT),
        ],
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = rav.version_from_source(ROOT, "portal")
    text = output.read_text()
    assert f"version={expected}\n" in text
    assert "version=9.9.9\n" not in text
