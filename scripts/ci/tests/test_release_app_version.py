"""Resolve component image versions from release tags or version files."""

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "release_app_version.py"

# Import the helpers directly so the assertions stay close to the contract.
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import release_app_version as rav  # noqa: E402


def test_version_from_component_tags():
    assert rav.version_from_tag("portal-v1.4.0", "portal") == "1.4.0"
    assert rav.version_from_tag("portal-v1.4.0-rc.1", "portal") == "1.4.0-rc.1"
    assert rav.version_from_tag("portal-v9.8.7+build.1", "portal") == "9.8.7+build.1"
    assert rav.version_from_tag("portal-v2.4.0-rc.1+build.1", "portal") == "2.4.0-rc.1+build.1"
    assert rav.version_from_tag("control-plane-ui-v1.13.0", "control-plane-ui") == "1.13.0"
    assert rav.version_from_tag("control-plane-api-v1.15.0", "control-plane-api") == "1.15.0"
    assert rav.version_from_tag("stoa-gateway-v0.9.27", "stoa-gateway") == "0.9.27"
    assert rav.version_from_tag("stoa-gateway-v0.9.27-rc.1", "stoa-gateway") == "0.9.27-rc.1"
    assert rav.version_from_tag("stoa-gateway-v0.9.27+build.1", "stoa-gateway") == "0.9.27+build.1"
    assert (
        rav.version_from_tag("stoa-gateway-v0.9.27-rc.1+build.1", "stoa-gateway")
        == "0.9.27-rc.1+build.1"
    )


def test_version_from_tag_rejects_mismatched_or_invalid_tags():
    assert rav.version_from_tag("control-plane-ui-v1.13.0", "portal") is None
    assert rav.version_from_tag("portal-v1.4.0", "control-plane-api") is None
    assert rav.version_from_tag("portal-v1.4.0", "stoa-gateway") is None
    assert rav.version_from_tag("v1.4.0", "portal") is None
    assert rav.version_from_tag("v0.9.27", "stoa-gateway") is None
    assert rav.version_from_tag("portal-v", "portal") is None
    assert rav.version_from_tag("portal-v2.4", "portal") is None
    assert rav.version_from_tag("stoa-gateway-v0.9", "stoa-gateway") is None
    assert rav.version_from_tag("main", "portal") is None
    assert rav.version_from_tag("portal-vnot-a-version", "portal") is None
    for bad in (
        "portal-v2.4.0garbage",
        "portal-v2.4.0-",
        "portal-v2.4.0+",
        "portal-v02.4.0",
        "portal-v2.4.0-01",
        "portal-v2.4.0-rc.",
        "portal-v2.4.0+build.",
        "portal-v2.4.0\n",
    ):
        assert rav.version_from_tag(bad, "portal") is None, bad
        gw_bad = bad.replace("portal-v", "stoa-gateway-v", 1)
        assert rav.version_from_tag(gw_bad, "stoa-gateway") is None, gw_bad


def test_version_from_platform_tags():
    assert rav.version_from_platform_tag("v2.4.0") == "2.4.0"
    assert rav.version_from_platform_tag("v2.4.0-rc.1") == "2.4.0-rc.1"
    assert rav.version_from_platform_tag("v2.4.0+build.1") == "2.4.0+build.1"
    assert rav.version_from_platform_tag("v2.4.0-rc.1+build.1") == "2.4.0-rc.1+build.1"
    for bad in (
        "",
        "v",
        "v2.4",
        "vnot-a-version",
        "v2.4.0garbage",
        "v2.4.0-",
        "v2.4.0+",
        "v02.4.0",
        "v2.4.0-01",
        "v2.4.0-rc.",
        "v2.4.0+build.",
        "v2.4.0\n",
        "2.4.0",
        "2.4.0garbage",
        "2.4.0-",
        "2.4.0+",
        "portal-v1.4.0",
        "control-plane-ui-v1.13.0",
        "main",
    ):
        assert rav.version_from_platform_tag(bad) is None, bad


def test_version_from_source_reads_checked_out_files():
    assert rav.version_from_source(ROOT, "portal") == json.loads(
        (ROOT / "portal" / "package.json").read_text()
    )["version"]
    assert rav.version_from_source(ROOT, "control-plane-ui") == json.loads(
        (ROOT / "control-plane-ui" / "package.json").read_text()
    )["version"]
    expected = tomllib.loads(
        (ROOT / "control-plane-api" / "pyproject.toml").read_text()
    )["project"]["version"]
    assert rav.version_from_source(ROOT, "control-plane-api") == expected
    expected_gw = tomllib.loads(
        (ROOT / "stoa-gateway" / "Cargo.toml").read_text()
    )["package"]["version"]
    assert rav.version_from_source(ROOT, "stoa-gateway") == expected_gw
    assert rav.version_from_source(ROOT, "keycloak") == "0.0.0-dev"


@pytest.mark.parametrize("service", ["portal", "control-plane-ui"])
@pytest.mark.parametrize(
    "manifest",
    [{}, {"version": None}, {"version": ""}, {"version": "   \t\n"}],
)
def test_version_from_source_frontend_missing_or_blank_falls_back_to_dev(
    tmp_path, service, manifest
):
    pkg = tmp_path / service / "package.json"
    pkg.parent.mkdir(parents=True)
    pkg.write_text(json.dumps(manifest), encoding="utf-8")
    assert rav.version_from_source(tmp_path, service) == "0.0.0-dev"
    assert rav.resolve_app_version(
        service, "main", tmp_path, event_name="workflow_dispatch"
    ) == ("0.0.0-dev", True)


@pytest.mark.parametrize(
    "pyproject_text",
    [
        "",
        '[project]\nname = "control-plane-api"\n',
        '[project]\nname = "control-plane-api"\nversion = ""\n',
        '[project]\nname = "control-plane-api"\nversion = "   \\t "\n',
    ],
)
def test_version_from_source_api_missing_or_blank_falls_back_to_dev(
    tmp_path, pyproject_text
):
    pyproject = tmp_path / "control-plane-api" / "pyproject.toml"
    pyproject.parent.mkdir(parents=True)
    pyproject.write_text(pyproject_text, encoding="utf-8")
    assert rav.version_from_source(tmp_path, "control-plane-api") == "0.0.0-dev"
    assert rav.resolve_app_version(
        "control-plane-api", "main", tmp_path, event_name="workflow_call"
    ) == ("0.0.0-dev", True)


@pytest.mark.parametrize(
    "cargo_text",
    [
        "",
        '[package]\nname = "stoa-gateway"\n',
        '[package]\nname = "stoa-gateway"\nversion = ""\n',
        '[package]\nname = "stoa-gateway"\nversion = "   \\t "\n',
    ],
)
def test_version_from_source_gateway_missing_or_blank_falls_back_to_dev(
    tmp_path, cargo_text
):
    cargo = tmp_path / "stoa-gateway" / "Cargo.toml"
    cargo.parent.mkdir(parents=True)
    cargo.write_text(cargo_text, encoding="utf-8")
    assert rav.version_from_source(tmp_path, "stoa-gateway") == "0.0.0-dev"
    assert rav.resolve_app_version(
        "stoa-gateway", "main", tmp_path, event_name="workflow_dispatch"
    ) == ("0.0.0-dev", True)


def test_version_from_source_gateway_rejects_invalid_package_or_workspace_version(tmp_path):
    cargo = tmp_path / "stoa-gateway" / "Cargo.toml"
    cargo.parent.mkdir(parents=True)

    cargo.write_text('package = "not-a-table"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid \\[package\\] section"):
        rav.version_from_source(tmp_path, "stoa-gateway")

    cargo.write_text("[package]\nversion = { workspace = true }\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid version"):
        rav.version_from_source(tmp_path, "stoa-gateway")


@pytest.mark.parametrize(
    "valid_version",
    ["2.4.0", "2.4.0-rc.1", "2.4.0+build.1", "2.4.0-rc.1+build.1"],
)
def test_version_from_source_accepts_valid_semver(tmp_path, valid_version):
    portal_pkg = tmp_path / "portal" / "package.json"
    portal_pkg.parent.mkdir(parents=True)
    portal_pkg.write_text(json.dumps({"version": valid_version}), encoding="utf-8")
    assert rav.version_from_source(tmp_path, "portal") == valid_version

    api_pyproject = tmp_path / "control-plane-api" / "pyproject.toml"
    api_pyproject.parent.mkdir(parents=True)
    api_pyproject.write_text(
        f"[project]\nversion = {json.dumps(valid_version)}\n", encoding="utf-8"
    )
    assert rav.version_from_source(tmp_path, "control-plane-api") == valid_version

    gw_cargo = tmp_path / "stoa-gateway" / "Cargo.toml"
    gw_cargo.parent.mkdir(parents=True)
    gw_cargo.write_text(
        f"[package]\nversion = {json.dumps(valid_version)}\n", encoding="utf-8"
    )
    assert rav.version_from_source(tmp_path, "stoa-gateway") == valid_version


@pytest.mark.parametrize(
    "bad_version",
    [
        "not-a-version",
        "1.2",
        "2.4",
        "2.4.0garbage",
        "2.4.0-",
        "2.4.0+",
        "02.4.0",
        "2.4.0-01",
        "2.4.0-rc.",
        "2.4.0+build.",
        123,
    ],
)
def test_version_from_source_rejects_present_invalid_version(tmp_path, bad_version):
    portal_pkg = tmp_path / "portal" / "package.json"
    portal_pkg.parent.mkdir(parents=True)
    portal_pkg.write_text(json.dumps({"version": bad_version}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid version"):
        rav.version_from_source(tmp_path, "portal")

    api_pyproject = tmp_path / "control-plane-api" / "pyproject.toml"
    api_pyproject.parent.mkdir(parents=True)
    raw = json.dumps(bad_version)
    api_pyproject.write_text(f"[project]\nversion = {raw}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid version"):
        rav.version_from_source(tmp_path, "control-plane-api")

    gw_cargo = tmp_path / "stoa-gateway" / "Cargo.toml"
    gw_cargo.parent.mkdir(parents=True)
    gw_cargo.write_text(f"[package]\nversion = {raw}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid version"):
        rav.version_from_source(tmp_path, "stoa-gateway")


def test_resolve_prefers_matching_tag_over_version_file():
    version, verify = rav.resolve_app_version("portal", "portal-v9.9.9", ROOT, event_name="release")
    assert version == "9.9.9"
    assert verify is True

    prerelease, verify_pre = rav.resolve_app_version(
        "portal", "portal-v9.9.9-rc.1", ROOT, event_name="release"
    )
    assert prerelease == "9.9.9-rc.1"
    assert verify_pre is True

    build_meta, verify_build = rav.resolve_app_version(
        "portal", "portal-v9.8.7+build.1", ROOT, event_name="release"
    )
    assert build_meta == "9.8.7+build.1"
    assert verify_build is True

    pre_build, verify_pre_build = rav.resolve_app_version(
        "portal", "portal-v9.8.7-rc.1+build.1", ROOT, event_name="release"
    )
    assert pre_build == "9.8.7-rc.1+build.1"
    assert verify_pre_build is True

    gw_version, gw_verify = rav.resolve_app_version(
        "stoa-gateway", "stoa-gateway-v0.9.99", ROOT, event_name="release"
    )
    assert gw_version == "0.9.99"
    assert gw_verify is True


@pytest.mark.parametrize(
    "service",
    ["portal", "control-plane-ui", "control-plane-api", "stoa-gateway", "keycloak"],
)
@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v2.4.0", "2.4.0"),
        ("v2.4.0-rc.1", "2.4.0-rc.1"),
        ("v2.4.0+build.1", "2.4.0+build.1"),
        ("v2.4.0-rc.1+build.1", "2.4.0-rc.1+build.1"),
    ],
)
def test_resolve_release_injects_platform_tag_for_versioned_services(
    service, tag, expected, tmp_path
):
    version, verify = rav.resolve_app_version(service, tag, ROOT, event_name="release")
    assert version == expected
    assert verify is True

    output = tmp_path / f"output-{service}-{expected}"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            service,
            "--tag",
            tag,
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
    assert f"version={expected}\n" in text
    assert "verify=true\n" in text
    if service == "stoa-gateway":
        assert "build_args=\n" in text
        assert "APP_VERSION=" not in text
        assert "VITE_APP_VERSION=" not in text
    else:
        assert f"APP_VERSION={expected}" in text
        if service in ("portal", "control-plane-ui"):
            assert f"VITE_APP_VERSION={expected}" in text
        else:
            assert "VITE_APP_VERSION=" not in text


@pytest.mark.parametrize(
    "service",
    ["portal", "control-plane-ui", "control-plane-api", "stoa-gateway", "keycloak"],
)
@pytest.mark.parametrize(
    "suffix",
    ["2.4.0garbage", "2.4.0-", "2.4.0+", "9.8", "", "02.4.0", "2.4.0-01"],
)
def test_resolve_rejects_malformed_component_release_tags(service, suffix, tmp_path):
    bad_tag = f"{service}-v{suffix}"
    with pytest.raises(ValueError, match="Invalid component release tag"):
        rav.resolve_app_version(service, bad_tag, ROOT, event_name="release")

    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            service,
            "--tag",
            bad_tag,
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
    assert result.returncode == 1
    assert "::error::Failed to resolve application version:" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "service",
    ["portal", "control-plane-ui", "control-plane-api", "stoa-gateway", "keycloak"],
)
@pytest.mark.parametrize(
    "bad_tag",
    [
        "v",
        "v2.4",
        "vnot-a-version",
        "v2.4.0garbage",
        "v2.4.0-",
        "v2.4.0+",
        "v02.4.0",
        "v2.4.0-01",
    ],
)
def test_resolve_rejects_malformed_platform_release_tags(service, bad_tag, tmp_path):
    with pytest.raises(ValueError, match="Invalid platform release tag"):
        rav.resolve_app_version(service, bad_tag, ROOT, event_name="release")

    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            service,
            "--tag",
            bad_tag,
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
    assert result.returncode == 1
    assert "::error::Failed to resolve application version:" in result.stderr
    assert not output.exists()


def test_resolve_release_other_component_tag_uses_source_or_dev_fallback(tmp_path):
    version, verify = rav.resolve_app_version(
        "portal", "control-plane-ui-v1.13.0", ROOT, event_name="release"
    )
    assert version == rav.version_from_source(ROOT, "portal")
    assert verify is True

    blank_pkg = tmp_path / "portal" / "package.json"
    blank_pkg.parent.mkdir(parents=True)
    blank_pkg.write_text(json.dumps({"version": "   "}), encoding="utf-8")
    fallback, verify_fallback = rav.resolve_app_version(
        "portal", "control-plane-ui-v1.13.0", tmp_path, event_name="release"
    )
    assert fallback == "0.0.0-dev"
    assert verify_fallback is True

    gw_version, gw_verify = rav.resolve_app_version(
        "stoa-gateway", "portal-v1.4.0", ROOT, event_name="release"
    )
    assert gw_version == rav.version_from_source(ROOT, "stoa-gateway")
    assert gw_verify is True

    kc_version, kc_verify = rav.resolve_app_version(
        "keycloak", "portal-v1.4.0", ROOT, event_name="release"
    )
    assert kc_version == "0.0.0-dev"
    assert kc_verify is True


@pytest.mark.parametrize("service", ["portal", "stoa-gateway", "keycloak"])
@pytest.mark.parametrize("event_name", ["workflow_dispatch", "workflow_call"])
@pytest.mark.parametrize(
    "tag_template",
    [
        "{service}-v9.9.9",
        "{service}-v9.8",
        "{service}-v9.8.7+build.1",
        "{service}-v2.4.0garbage",
        "{service}-v2.4.0-",
        "{service}-v2.4.0+",
        "v2.4.0",
        "v2.4",
        "v",
        "vnot-a-version",
        "v2.4.0garbage",
        "v2.4.0-",
        "v2.4.0+",
    ],
)
def test_resolve_non_release_events_ignore_component_and_platform_tags(
    service, event_name, tag_template
):
    tag = tag_template.format(service=service)
    version, verify = rav.resolve_app_version(service, tag, ROOT, event_name=event_name)
    assert version == rav.version_from_source(ROOT, service)
    assert verify is True


def test_resolve_falls_back_to_version_file_when_tag_is_not_component_scoped():
    version, verify = rav.resolve_app_version("portal", "main", ROOT, event_name="workflow_dispatch")
    assert version == rav.version_from_source(ROOT, "portal")
    assert verify is True

    gw_version, gw_verify = rav.resolve_app_version(
        "stoa-gateway", "main", ROOT, event_name="workflow_dispatch"
    )
    assert gw_version == rav.version_from_source(ROOT, "stoa-gateway")
    assert gw_verify is True

    kc_version, kc_verify = rav.resolve_app_version(
        "keycloak", "main", ROOT, event_name="workflow_dispatch"
    )
    assert kc_version == "0.0.0-dev"
    assert kc_verify is True


def test_resolve_skips_unversioned_services():
    assert rav.resolve_app_version("stoa-go", "stoa-go-v1.0.0", ROOT) == ("", False)
    assert rav.resolve_app_version("stoa-go", "v2.4.0", ROOT, event_name="release") == ("", False)
    assert rav.resolve_app_version("stoa-go", "v2.4.0garbage", ROOT, event_name="release") == (
        "",
        False,
    )
    assert rav.resolve_app_version("unknown-service", "v2.4.0", ROOT, event_name="release") == (
        "",
        False,
    )


def test_build_args_only_for_build_arg_consuming_services():
    assert rav.build_args_for("portal", "1.4.0") == (
        "APP_VERSION=1.4.0\nVITE_APP_VERSION=1.4.0\n"
    )
    assert rav.build_args_for("control-plane-ui", "1.13.0") == (
        "APP_VERSION=1.13.0\nVITE_APP_VERSION=1.13.0\n"
    )
    assert rav.build_args_for("control-plane-api", "1.15.0") == "APP_VERSION=1.15.0\n"
    assert rav.build_args_for("keycloak", "2.4.0") == "APP_VERSION=2.4.0\n"
    assert rav.build_args_for("stoa-gateway", "0.9.27") == ""
    assert rav.build_args_for("unknown-service", "1.0.0") == ""


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


@pytest.mark.parametrize("service", ["portal", "stoa-gateway"])
def test_cli_errors_when_fallback_file_is_missing(service, tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            service,
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

    gw_version, gw_verify = rav.resolve_app_version(
        "stoa-gateway", "stoa-gateway-v9.9.9", ROOT, event_name="workflow_dispatch"
    )
    assert gw_version == rav.version_from_source(ROOT, "stoa-gateway")
    assert gw_version != "9.9.9"
    assert gw_verify is True

    kc_version, kc_verify = rav.resolve_app_version(
        "keycloak", "v9.9.9", ROOT, event_name="workflow_dispatch"
    )
    assert kc_version == "0.0.0-dev"
    assert kc_verify is True


def test_resolve_ignores_tag_when_event_name_is_missing():
    version, verify = rav.resolve_app_version("portal", "portal-v9.9.9", ROOT)
    assert version == rav.version_from_source(ROOT, "portal")
    assert verify is True

    gw_version, gw_verify = rav.resolve_app_version("stoa-gateway", "stoa-gateway-v9.9.9", ROOT)
    assert gw_version == rav.version_from_source(ROOT, "stoa-gateway")
    assert gw_verify is True

    kc_version, kc_verify = rav.resolve_app_version("keycloak", "v9.9.9", ROOT)
    assert kc_version == "0.0.0-dev"
    assert kc_verify is True


@pytest.mark.parametrize(
    "service,tag",
    [
        ("portal", "portal-v9.9.9"),
        ("stoa-gateway", "stoa-gateway-v9.9.9"),
        ("keycloak", "v9.9.9"),
    ],
)
def test_cli_dispatch_ignores_tag_shaped_ref(service, tag, tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--service",
            service,
            "--tag",
            tag,
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
    expected = rav.version_from_source(ROOT, service)
    text = output.read_text()
    assert f"version={expected}\n" in text
    assert "verify=true\n" in text
    assert "version=9.9.9\n" not in text
    if service == "keycloak":
        assert "APP_VERSION=0.0.0-dev" in text
    elif service == "stoa-gateway":
        assert "build_args=\n" in text


def test_docker_publish_all_services_match_versioned_services():
    workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(encoding="utf-8")
    match = re.search(r"ALL_SERVICES='(\[[^\n']+\])'", workflow)
    assert match is not None
    all_services = json.loads(match.group(1))
    assert set(all_services) == set(rav.VERSIONED_SERVICES)
