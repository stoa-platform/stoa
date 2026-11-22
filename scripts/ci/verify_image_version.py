#!/usr/bin/env python3
"""Check that a built component image serves the expected application version."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from html.parser import HTMLParser
from pathlib import Path

VERSIONED_SERVICES = ("control-plane-api", "control-plane-ui", "portal")
FRONTEND_HTML_ROOT = "/usr/share/nginx/html"
FRONTEND_VERSION_PATH = f"{FRONTEND_HTML_ROOT}/version.txt"
FRONTEND_INDEX_PATH = f"{FRONTEND_HTML_ROOT}/index.html"
FRONTEND_MARK_PREFIX = "stoa-app-version:"
API_HEALTH_PATH = "/health"

_EXECUTABLE_SCRIPT_TYPES = frozenset(
    {
        "",
        "module",
        "text/javascript",
        "application/javascript",
        "text/ecmascript",
        "application/ecmascript",
    }
)
_REGEX_PREFIX_KEYWORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)

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


def frontend_app_mark(expected: str) -> str:
    return f"{FRONTEND_MARK_PREFIX}{expected}"


def assert_safe_version_token(expected: str) -> None:
    if not re.fullmatch(r"[0-9A-Za-z._+-]+", expected):
        raise ValueError(f"Unsafe application version token: {expected!r}")


def _is_runtime_config_ref(path: str) -> bool:
    normalized = path.strip().lower()
    return normalized == "runtime-config.js" or normalized.endswith("/runtime-config.js")


class _ExecutableScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []
        self._template_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name == "template":
            self._template_depth += 1
            return
        if self._template_depth > 0 or tag_name != "script":
            return
        attr_map = {name.lower(): (value or "") for name, value in attrs}
        script_type = attr_map.get("type", "").split(";", 1)[0].strip().lower()
        if script_type not in _EXECUTABLE_SCRIPT_TYPES:
            return
        src = attr_map.get("src", "").strip()
        if not src:
            return
        path = src.split("#", 1)[0].split("?", 1)[0].strip()
        if _is_runtime_config_ref(path):
            return
        if path.endswith((".js", ".mjs")):
            self.refs.append(path)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "template" and self._template_depth > 0:
            self._template_depth -= 1


def application_script_refs(index_html: str) -> list[str]:
    """Return executable <script src=...> JavaScript files from index.html."""
    parser = _ExecutableScriptParser()
    parser.feed(strip_html_comments(index_html))
    parser.close()
    return parser.refs


def resolve_frontend_path(href: str) -> str:
    relative = href.split("#", 1)[0].split("?", 1)[0].lstrip("/")
    if relative.startswith("./"):
        relative = relative[2:]
    parts = Path(relative).parts
    if not relative or ".." in parts:
        raise VersionMismatch(f"Refusing unsafe script path: {href!r}")
    return f"{FRONTEND_HTML_ROOT}/{relative}"


def _scan_js(source: str, *, target_literal: str | None = None) -> tuple[str, bool]:
    """Strip JS // and /* */ comments while scanning string, template, and regex literals."""
    out: list[str] = []
    n = len(source)
    i = 0
    allows_regex = True
    brace_stack: list[bool] = []
    paren_stack: list[bool] = []
    prev_word = ""
    found = False

    def scan_template(pos: int, *, standalone: bool) -> tuple[int, bool]:
        nonlocal found
        start = pos
        while pos < n:
            ch = source[pos]
            if ch == "\\" and pos + 1 < n:
                out.append(source[pos : pos + 2])
                pos += 2
                continue
            if ch == "`":
                if standalone and target_literal is not None and source[start:pos] == target_literal:
                    found = True
                out.append(ch)
                return pos + 1, False
            if ch == "$" and pos + 1 < n and source[pos + 1] == "{":
                out.append("${")
                brace_stack.append(True)
                return pos + 2, True
            out.append(ch)
            pos += 1
        return pos, False

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if ch in " \t\r\n":
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            i += 2
            while i < n and source[i] not in "\r\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            end = source.find("*/", i)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue

        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            start = i
            while i < n:
                c = source[i]
                if c == "\\" and i + 1 < n:
                    out.append(source[i : i + 2])
                    i += 2
                    continue
                out.append(c)
                if c == quote:
                    if target_literal is not None and source[start:i] == target_literal:
                        found = True
                    i += 1
                    break
                i += 1
            allows_regex = False
            prev_word = ""
            continue

        if ch == "`":
            out.append(ch)
            i, entered_expr = scan_template(i + 1, standalone=True)
            allows_regex = entered_expr
            prev_word = ""
            continue

        if ch == "{":
            out.append(ch)
            brace_stack.append(False)
            allows_regex = True
            prev_word = ""
            i += 1
            continue

        if ch == "}":
            out.append(ch)
            i += 1
            if brace_stack and brace_stack.pop():
                i, entered_expr = scan_template(i, standalone=False)
                allows_regex = entered_expr
            else:
                allows_regex = False
            prev_word = ""
            continue

        if ch == "/":
            if allows_regex:
                out.append(ch)
                i += 1
                in_class = False
                while i < n:
                    c = source[i]
                    if c == "\\" and i + 1 < n:
                        out.append(source[i : i + 2])
                        i += 2
                        continue
                    if c == "[":
                        in_class = True
                    elif c == "]":
                        in_class = False
                    elif c == "/" and not in_class:
                        out.append(c)
                        i += 1
                        break
                    elif c in "\r\n":
                        break
                    out.append(c)
                    i += 1
                allows_regex = False
            else:
                out.append(ch)
                i += 1
                allows_regex = True
            prev_word = ""
            continue

        if ch.isalpha() or ch in "_$":
            start = i
            i += 1
            while i < n and (source[i].isalnum() or source[i] in "_$"):
                i += 1
            word = source[start:i]
            out.append(word)
            allows_regex = word in _REGEX_PREFIX_KEYWORDS
            prev_word = word
            continue

        if ch.isdigit():
            start = i
            i += 1
            while i < n and (source[i].isalnum() or source[i] in "._"):
                i += 1
            out.append(source[start:i])
            allows_regex = False
            prev_word = ""
            continue

        if ch == "(":
            out.append(ch)
            paren_stack.append(prev_word in ("if", "while", "for", "with"))
            allows_regex = True
            prev_word = ""
            i += 1
            continue

        if ch == ")":
            out.append(ch)
            allows_regex = paren_stack.pop() if paren_stack else False
            prev_word = ""
            i += 1
            continue

        if ch in "].":
            out.append(ch)
            allows_regex = False
            prev_word = ""
            i += 1
            continue

        if ch in "+-" and nxt == ch:
            out.append(source[i : i + 2])
            allows_regex = False
            prev_word = ""
            i += 2
            continue

        out.append(ch)
        allows_regex = True
        prev_word = ""
        i += 1

    return "".join(out), found


def strip_js_comments(source: str) -> str:
    """Strip JS // and /* */ comments while preserving string, template, and regex literals."""
    cleaned, _ = _scan_js(source)
    return cleaned


def has_delimited_app_mark(content: str, expected: str) -> bool:
    """Require an exact string or uninterpolated template literal equal to the app mark."""
    assert_safe_version_token(expected)
    _, found = _scan_js(content, target_literal=frontend_app_mark(expected))
    return found


def scan_application_scripts_for_mark(
    index_html: str,
    scripts: dict[str, str],
    expected: str,
) -> str:
    mark = frontend_app_mark(expected)
    refs = application_script_refs(index_html)
    if not refs:
        raise VersionMismatch("index.html does not load any application JavaScript")
    for href in refs:
        path = resolve_frontend_path(href)
        if path not in scripts:
            raise VersionMismatch(f"application script {path} was missing")
        if has_delimited_app_mark(scripts[path], expected):
            return mark
    raise VersionMismatch(
        f"application mark {mark!r} was not found in JavaScript loaded by the application"
    )


def read_frontend_app_mark(
    image_ref: str,
    expected: str,
    runner: Runner = default_runner,
) -> str:
    index_html = read_image_text(image_ref, FRONTEND_INDEX_PATH, runner=runner)
    scripts: dict[str, str] = {}
    for href in application_script_refs(index_html):
        path = resolve_frontend_path(href)
        scripts[path] = read_image_text(image_ref, path, runner=runner)
    return scan_application_scripts_for_mark(index_html, scripts, expected)


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
        read_frontend_app_mark(image_ref, expected, runner=runner)
        compare_version(
            served_frontend_version(image_ref, runner=runner, wait=wait),
            expected,
            "frontend /version.txt",
        )
        return
    compare_version(
        served_api_health_version(image_ref, runner=runner, wait=wait),
        expected,
        "API /health",
    )


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
