"""Pure-function tests for the pre-push image version check."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import verify_image_version as viv  # noqa: E402


class FakeRunner:
    def __init__(self, responses: list[tuple[tuple[str, ...], SimpleNamespace]]):
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        key = tuple(argv)
        for expected, result in self.responses:
            if key == expected:
                return result
        # allow docker rm -f to be ignored
        if argv[:3] == ["docker", "rm", "-f"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {argv}")


def _ok(stdout=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_first_image_tag_and_health_parser():
    tags = "ghcr.io/stoa-platform/portal:1.4.0\nghcr.io/stoa-platform/portal:sha-deadbeef\n"
    assert viv.first_image_tag(tags) == "ghcr.io/stoa-platform/portal:1.4.0"
    with pytest.raises(ValueError):
        viv.first_image_tag("\n")
    assert viv.parse_health_version('{"status": "healthy", "version": "1.15.0"}') == "1.15.0"
    with pytest.raises(ValueError):
        viv.parse_health_version('{"status": "healthy"}')


def test_compare_version_fail_closed():
    viv.compare_version("1.4.0\n", "1.4.0", "file")
    with pytest.raises(viv.VersionMismatch, match="expected '1.4.0'"):
        viv.compare_version("1.0.0", "1.4.0", "file")


def test_read_frontend_version_file_uses_cat():
    runner = FakeRunner([
        (
            (
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                "img:tag",
                "/usr/share/nginx/html/version.txt",
            ),
            _ok("1.13.0\n"),
        )
    ])
    assert viv.read_frontend_version_file("img:tag", runner=runner) == "1.13.0"


def test_verify_frontend_mismatch_fails_before_starting_server():
    runner = FakeRunner([
        (
            (
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                "img:tag",
                "/usr/share/nginx/html/version.txt",
            ),
            _ok("2.0.0\n"),
        )
    ])
    with pytest.raises(viv.VersionMismatch, match="expected '1.13.0'"):
        viv.verify_image_version("control-plane-ui", "1.13.0", "img:tag", runner=runner)
    assert not any(call[:2] == ["docker", "run"] and "-d" in call for call in runner.calls)


def test_verify_api_health_success():
    inspect_payload = json.dumps([
        {"NetworkSettings": {"Ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}}}
    ])
    runner = FakeRunner([
        (
            (
                "docker",
                "run",
                "-d",
                "--name",
                "stoa-version-check-api",
                "-p",
                "127.0.0.1::8000",
                "-e",
                "ENVIRONMENT=test",
                "-e",
                "STOA_ENABLE_KAFKA_CONSUMERS=false",
                "-e",
                "ENABLE_GATEWAY_HEALTH_WORKER=false",
                "-e",
                "ENABLE_TELEMETRY_WORKER=false",
                "-e",
                "ENABLE_GATEWAY_RECONCILER=false",
                "-e",
                "ENABLE_CATALOG_RECONCILER=false",
                "-e",
                "KAFKA_ENABLED=false",
                "-e",
                "GITHUB_TOKEN=ci-dummy",
                "-e",
                "GIT_PROVIDER=github",
                "-e",
                "GITHUB_ORG=stoa-platform",
                "-e",
                "GITHUB_CATALOG_REPO=stoa-catalog",
                "img:tag",
                "uvicorn",
                "src.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--lifespan",
                "off",
            ),
            _ok("cid\n"),
        ),
        (("docker", "inspect", "stoa-version-check-api"), _ok(inspect_payload)),
    ])

    def fake_wait(url, timeout_seconds, **kwargs):
        assert url == "http://127.0.0.1:34567/health"
        return '{"status": "healthy", "version": "1.15.0"}'

    viv.verify_image_version("control-plane-api", "1.15.0", "img:tag", runner=runner, wait=fake_wait)
    assert ["docker", "rm", "-f", "stoa-version-check-api"] in runner.calls


def test_verify_api_health_mismatch():
    inspect_payload = json.dumps([
        {"NetworkSettings": {"Ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}}}
    ])
    runner = FakeRunner([
        (
            (
                "docker",
                "run",
                "-d",
                "--name",
                "stoa-version-check-api",
                "-p",
                "127.0.0.1::8000",
                "-e",
                "ENVIRONMENT=test",
                "-e",
                "STOA_ENABLE_KAFKA_CONSUMERS=false",
                "-e",
                "ENABLE_GATEWAY_HEALTH_WORKER=false",
                "-e",
                "ENABLE_TELEMETRY_WORKER=false",
                "-e",
                "ENABLE_GATEWAY_RECONCILER=false",
                "-e",
                "ENABLE_CATALOG_RECONCILER=false",
                "-e",
                "KAFKA_ENABLED=false",
                "-e",
                "GITHUB_TOKEN=ci-dummy",
                "-e",
                "GIT_PROVIDER=github",
                "-e",
                "GITHUB_ORG=stoa-platform",
                "-e",
                "GITHUB_CATALOG_REPO=stoa-catalog",
                "img:tag",
                "uvicorn",
                "src.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--lifespan",
                "off",
            ),
            _ok("cid\n"),
        ),
        (("docker", "inspect", "stoa-version-check-api"), _ok(inspect_payload)),
    ])

    def fake_wait(url, timeout_seconds, **kwargs):
        return '{"status": "healthy", "version": "2.0.0"}'

    with pytest.raises(viv.VersionMismatch, match="expected '1.15.0'"):
        viv.verify_image_version("control-plane-api", "1.15.0", "img:tag", runner=runner, wait=fake_wait)
    assert ["docker", "rm", "-f", "stoa-version-check-api"] in runner.calls


def test_verify_skips_unversioned_services():
    runner = FakeRunner([])
    viv.verify_image_version("keycloak", "ignored", "img:tag", runner=runner)
    assert runner.calls == []

def test_extract_meta_app_version():
    html = """<!doctype html><html><head>
    <meta name="stoa-app-version" content="1.13.0" />
    </head><body></body></html>"""
    assert viv.extract_meta_app_version(html) == "1.13.0"
    with pytest.raises(viv.VersionMismatch, match="missing the stoa-app-version meta tag"):
        viv.extract_meta_app_version("<html><head></head></html>")
    commented_meta = '<html><head><!-- <meta name="stoa-app-version" content="1.13.0" /> --></head></html>'
    with pytest.raises(viv.VersionMismatch, match="missing the stoa-app-version meta tag"):
        viv.extract_meta_app_version(commented_meta)


INDEX_HTML = """<!doctype html><html><head>
<meta name="stoa-app-version" content="1.13.0" />
<script type="module" src="/assets/index-abc.js"></script>
</head><body></body></html>
"""


def _frontend_file_ok(path, stdout):
    return (
        (
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "cat",
            "img:tag",
            path,
        ),
        _ok(stdout),
    )


def test_frontend_dockerfiles_handle_missing_or_null_package_version(tmp_path):
    pattern = re.compile(r"^RUN (VERSION=.*?) \\$", re.MULTILINE)
    assignments: list[str] = []
    for rel in ("portal/Dockerfile", "control-plane-ui/Dockerfile"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        match = pattern.search(text)
        assert match is not None, f"missing VERSION assignment in {rel}"
        assignment = match.group(1)
        assert "require('./package.json').version\")" not in assignment, rel
        assignments.append(assignment)
    assert assignments[0] == assignments[1]

    if shutil.which("node") is None:
        pytest.skip("node is not installed")

    shell_cmd = f'{assignments[0]} && printf "%s" "$VERSION"'
    cases = [
        ({"version": "1.4.0"}, {}, "1.4.0"),
        ({"version": " 1.4.0 "}, {}, "1.4.0"),
        ({}, {}, "0.0.0-dev"),
        ({"version": None}, {}, "0.0.0-dev"),
        ({"version": 123}, {}, "0.0.0-dev"),
        ({"version": ""}, {}, "0.0.0-dev"),
        ({"version": "   "}, {}, "0.0.0-dev"),
        ({}, {"APP_VERSION": "2.0.0"}, "2.0.0"),
        ({}, {"APP_VERSION": "2.0.0", "VITE_APP_VERSION": "3.0.0"}, "3.0.0"),
        ({}, {"APP_VERSION": "2.0.0", "VITE_APP_VERSION": "   "}, "2.0.0"),
        ({"version": "1.4.0"}, {"APP_VERSION": "   ", "VITE_APP_VERSION": "  "}, "1.4.0"),
        ({"version": "   "}, {"APP_VERSION": "   ", "VITE_APP_VERSION": "  "}, "0.0.0-dev"),
        ({}, {"APP_VERSION": "  2.0.0  "}, "2.0.0"),
        ({}, {"VITE_APP_VERSION": "  3.0.0  "}, "3.0.0"),
    ]
    base_env = {"PATH": os.environ.get("PATH", "")}
    for pkg, extra_env, expected in cases:
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        result = subprocess.run(
            ["/bin/sh", "-c", shell_cmd],
            cwd=tmp_path,
            env={**base_env, **extra_env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected


def test_api_dockerfile_normalizes_empty_app_version():
    text = (ROOT / "control-plane-api" / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG APP_VERSION=0.0.0-dev" in text
    assert "ENV VERSION=${APP_VERSION:-0.0.0-dev}" in text


def test_verify_frontend_stale_meta_fails_when_version_txt_is_correct():
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok(
            "/usr/share/nginx/html/index.html",
            '<meta name="stoa-app-version" content="2.0.0" />\n',
        ),
    ])
    with pytest.raises(viv.VersionMismatch, match="expected '1.13.0'"):
        viv.verify_image_version("portal", "1.13.0", "img:tag", runner=runner)
    assert not any(call[:2] == ["docker", "run"] and "-d" in call for call in runner.calls)


def test_verify_frontend_served_version_mismatch_fails_and_cleans_up():
    inspect_payload = json.dumps([
        {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}}}
    ])
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok("/usr/share/nginx/html/index.html", INDEX_HTML),
        (
            (
                "docker",
                "run",
                "-d",
                "--name",
                "stoa-version-check-ui",
                "-p",
                "127.0.0.1::8080",
                "img:tag",
            ),
            _ok("cid\n"),
        ),
        (("docker", "inspect", "stoa-version-check-ui"), _ok(inspect_payload)),
    ])

    def fake_wait(url, timeout_seconds, **kwargs):
        assert url == "http://127.0.0.1:34567/version.txt"
        return "2.0.0\n"

    with pytest.raises(viv.VersionMismatch, match="expected '1.13.0'"):
        viv.verify_image_version("portal", "1.13.0", "img:tag", runner=runner, wait=fake_wait)
    assert ["docker", "rm", "-f", "stoa-version-check-ui"] in runner.calls


def test_verify_frontend_success_checks_baked_files_and_served_version():
    inspect_payload = json.dumps([
        {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}}}
    ])
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok("/usr/share/nginx/html/index.html", INDEX_HTML),
        (
            (
                "docker",
                "run",
                "-d",
                "--name",
                "stoa-version-check-ui",
                "-p",
                "127.0.0.1::8080",
                "img:tag",
            ),
            _ok("cid\n"),
        ),
        (("docker", "inspect", "stoa-version-check-ui"), _ok(inspect_payload)),
    ])

    def fake_wait(url, timeout_seconds, **kwargs):
        assert url == "http://127.0.0.1:34567/version.txt"
        return "1.13.0\n"

    viv.verify_image_version("control-plane-ui", "1.13.0", "img:tag", runner=runner, wait=fake_wait)
    assert ["docker", "rm", "-f", "stoa-version-check-ui"] in runner.calls
    assert not any(call[-1].endswith((".js", ".mjs")) for call in runner.calls)
