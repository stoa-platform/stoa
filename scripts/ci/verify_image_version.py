#!/usr/bin/env python3
"""Check that a built component image serves the expected application version."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

VERSIONED_SERVICES = (
    "control-plane-api",
    "control-plane-ui",
    "keycloak",
    "portal",
    "stoa-gateway",
)
FRONTEND_HTML_ROOT = "/usr/share/nginx/html"
FRONTEND_VERSION_PATH = f"{FRONTEND_HTML_ROOT}/version.txt"
FRONTEND_INDEX_PATH = f"{FRONTEND_HTML_ROOT}/index.html"
API_HEALTH_PATH = "/health"
GATEWAY_DISCOVERY_PATH = "/mcp"
KEYCLOAK_VERSION_PATH = "/opt/keycloak/stoa-version.txt"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class VersionMismatch(RuntimeError):
    """Raised when the image does not serve the expected version."""


def first_image_tag(image_tags: str) -> str:
    for line in image_tags.splitlines():
        tag = line.strip()
        if tag:
            return tag
    raise ValueError("IMAGE_TAGS did not contain an image tag")


def parse_health_version(payload: str) -> str:
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        raise ValueError(f"Unexpected /health payload: {payload!r}")
    version = data["version"].strip()
    if not version:
        raise ValueError("Empty version in /health payload")
    return version


def parse_gateway_discovery_version(payload: str) -> str:
    data = json.loads(payload)
    server = data.get("server") if isinstance(data, dict) else None
    if not isinstance(server, dict) or not isinstance(server.get("version"), str):
        raise ValueError(f"Unexpected {GATEWAY_DISCOVERY_PATH} payload: {payload!r}")
    version = server["version"].strip()
    if not version:
        raise ValueError(f"Empty version in {GATEWAY_DISCOVERY_PATH} payload")
    return version


def compare_version(actual: str, expected: str, source: str) -> None:
    actual = actual.strip()
    if actual != expected:
        raise VersionMismatch(
            f"{source} reported version {actual!r}, expected {expected!r}"
        )


def default_runner(argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), check=False, text=True, capture_output=True, **kwargs)


def _require_ok(result: subprocess.CompletedProcess[str], action: str) -> subprocess.CompletedProcess[str]:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{action} failed ({result.returncode}): {detail}")
    return result


def _host_port(inspect_stdout: str, container_port: int) -> int:
    data = json.loads(inspect_stdout)
    if not isinstance(data, list) or not data:
        raise RuntimeError("docker inspect returned no container data")
    bindings = (
        data[0]
        .get("NetworkSettings", {})
        .get("Ports", {})
        .get(f"{container_port}/tcp")
        or []
    )
    if not bindings:
        raise RuntimeError(f"Container did not publish port {container_port}")
    host_port = bindings[0].get("HostPort")
    if not host_port:
        raise RuntimeError(f"Missing HostPort for {container_port}")
    return int(host_port)


def _fetch(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def wait_for_url(url: str, timeout_seconds: float, sleeper=time.sleep, fetcher=_fetch) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return fetcher(url, timeout=5)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            sleeper(1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def read_image_text(image_ref: str, path: str, runner: Runner = default_runner) -> str:
    result = _require_ok(
        runner(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                image_ref,
                path,
            ]
        ),
        f"read {path}",
    )
    return result.stdout or ""


def read_frontend_version_file(image_ref: str, runner: Runner = default_runner) -> str:
    version = read_image_text(image_ref, FRONTEND_VERSION_PATH, runner=runner).strip()
    if not version:
        raise VersionMismatch(f"{FRONTEND_VERSION_PATH} was empty")
    return version


def strip_html_comments(html: str) -> str:
    """Remove HTML comments, including an unclosed trailing comment."""
    return re.sub(r"<!--(?:.*?-->|.*$)", "", html, flags=re.DOTALL)


def extract_meta_app_version(html: str) -> str:
    cleaned = strip_html_comments(html)
    match = re.search(
        r'<meta\s+name="stoa-app-version"\s+content="([^"]*)"\s*/?>',
        cleaned,
        flags=re.IGNORECASE,
    )
    if match is None or not match.group(1).strip():
        raise VersionMismatch("index.html is missing the stoa-app-version meta tag")
    return match.group(1).strip()


def _run_and_cleanup(name: str, runner: Runner, body: Callable[[], str]) -> str:
    try:
        return body()
    finally:
        runner(["docker", "rm", "-f", name])


def served_frontend_version(
    image_ref: str,
    runner: Runner = default_runner,
    wait=wait_for_url,
) -> str:
    name = "stoa-version-check-ui"
    runner(["docker", "rm", "-f", name])
    _require_ok(
        runner(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-p",
                "127.0.0.1::8080",
                image_ref,
            ]
        ),
        "start frontend image",
    )

    def _body() -> str:
        inspect = _require_ok(
            runner(["docker", "inspect", name]),
            "inspect frontend container",
        )
        port = _host_port(inspect.stdout, 8080)
        payload = wait(f"http://127.0.0.1:{port}/version.txt", 30)
        return payload

    return _run_and_cleanup(name, runner, _body)


def served_api_health_version(
    image_ref: str,
    runner: Runner = default_runner,
    wait=wait_for_url,
) -> str:
    name = "stoa-version-check-api"
    runner(["docker", "rm", "-f", name])
    _require_ok(
        runner(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
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
                image_ref,
                "uvicorn",
                "src.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--lifespan",
                "off",
            ]
        ),
        "start API image",
    )

    def _body() -> str:
        inspect = _require_ok(
            runner(["docker", "inspect", name]),
            "inspect API container",
        )
        port = _host_port(inspect.stdout, 8000)
        payload = wait(f"http://127.0.0.1:{port}{API_HEALTH_PATH}", 90)
        return parse_health_version(payload)

    return _run_and_cleanup(name, runner, _body)


def read_copied_image_text(
    image_ref: str,
    path: str,
    container_name: str,
    runner: Runner = default_runner,
) -> str:
    runner(["docker", "rm", "-f", container_name])
    _require_ok(
        runner(["docker", "create", "--name", container_name, image_ref]),
        f"create container for {path}",
    )

    def _body() -> str:
        with tempfile.TemporaryDirectory(prefix="stoa-version-check-") as tmpdir:
            dest = Path(tmpdir) / Path(path).name
            _require_ok(
                runner(["docker", "cp", f"{container_name}:{path}", str(dest)]),
                f"copy {path}",
            )
            if dest.is_symlink() or not dest.is_file():
                raise VersionMismatch(f"{path} is not a regular file")
            return dest.read_text(encoding="utf-8")

    return _run_and_cleanup(container_name, runner, _body)


def read_keycloak_version_file(image_ref: str, runner: Runner = default_runner) -> str:
    version = read_copied_image_text(
        image_ref,
        KEYCLOAK_VERSION_PATH,
        "stoa-version-check-keycloak",
        runner=runner,
    ).strip()
    if not version:
        raise VersionMismatch(f"{KEYCLOAK_VERSION_PATH} was empty")
    return version


def served_gateway_version(
    image_ref: str,
    runner: Runner = default_runner,
    wait=wait_for_url,
) -> str:
    name = "stoa-version-check-gateway"
    runner(["docker", "rm", "-f", name])
    _require_ok(
        runner(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-p",
                "127.0.0.1::8080",
                "-e",
                "STOA_PORT=8080",
                "-e",
                "STOA_GATEWAY_MODE=edge-mcp",
                "-e",
                "STOA_ENVIRONMENT=dev",
                "-e",
                "STOA_AUTO_REGISTER=false",
                "-e",
                "STOA_OTEL_ENABLED=false",
                "-e",
                "STOA_KAFKA_ENABLED=false",
                "-e",
                "STOA_K8S_ENABLED=false",
                "-e",
                "STOA_ZOMBIE_DETECTION_ENABLED=false",
                "-e",
                "STOA_NATIVE_TOOLS_ENABLED=false",
                image_ref,
            ]
        ),
        "start gateway image",
    )

    def _body() -> str:
        inspect = _require_ok(
            runner(["docker", "inspect", name]),
            "inspect gateway container",
        )
        port = _host_port(inspect.stdout, 8080)
        payload = wait(f"http://127.0.0.1:{port}{GATEWAY_DISCOVERY_PATH}", 60)
        return parse_gateway_discovery_version(payload)

    return _run_and_cleanup(name, runner, _body)


def verify_image_version(
    service: str,
    expected: str,
    image_ref: str,
    runner: Runner = default_runner,
    wait=wait_for_url,
) -> None:
    if service not in VERSIONED_SERVICES:
        return
    if not expected:
        raise ValueError("Expected application version is empty")
    if service in ("control-plane-ui", "portal"):
        compare_version(
            read_frontend_version_file(image_ref, runner=runner),
            expected,
            FRONTEND_VERSION_PATH,
        )
        compare_version(
            extract_meta_app_version(
                read_image_text(image_ref, FRONTEND_INDEX_PATH, runner=runner)
            ),
            expected,
            "index.html stoa-app-version meta",
        )
        compare_version(
            served_frontend_version(image_ref, runner=runner, wait=wait),
            expected,
            "frontend /version.txt",
        )
        return
    if service == "control-plane-api":
        compare_version(
            served_api_health_version(image_ref, runner=runner, wait=wait),
            expected,
            "API /health",
        )
        return
    if service == "stoa-gateway":
        compare_version(
            served_gateway_version(image_ref, runner=runner, wait=wait),
            expected,
            f"gateway {GATEWAY_DISCOVERY_PATH}",
        )
        return
    if service == "keycloak":
        compare_version(
            read_keycloak_version_file(image_ref, runner=runner),
            expected,
            KEYCLOAK_VERSION_PATH,
        )
        return
    raise ValueError(f"Unsupported versioned service {service!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=os.environ.get("SERVICE", ""))
    parser.add_argument("--version", default=os.environ.get("APP_VERSION", ""))
    parser.add_argument("--image-tags", default=os.environ.get("IMAGE_TAGS", ""))
    args = parser.parse_args(argv)

    if args.service not in VERSIONED_SERVICES:
        return 0
    try:
        image_ref = first_image_tag(args.image_tags)
        verify_image_version(args.service, args.version, image_ref)
    except (VersionMismatch, ValueError, RuntimeError, json.JSONDecodeError, OSError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"Image version check passed for {args.service}: {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
