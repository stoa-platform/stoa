"""Pure-function tests for the pre-push image version check."""

import json
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


INDEX_HTML = """<!doctype html><html><head>
<meta name="stoa-app-version" content="1.13.0" />
<script type="module" src="/assets/index-abc.js"></script>
</head><body></body></html>
"""
JS_PATH = "/usr/share/nginx/html/assets/index-abc.js"


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


def test_application_script_refs_ignore_unrelated_assets():
    html = """<html><head>
    <link rel="stylesheet" href="/assets/index.css">
    <link rel="modulepreload" href="/assets/vendor.js">
    <link rel="preload" as="script" href="/assets/preload.js">
    <script type="application/json" src="/assets/data.js"></script>
    <!-- <script type="module" src="/assets/commented.js"></script> -->
    <script src="/assets/classic.js"></script>
    <script type="module" src="./assets/index-abc.js"></script>
    </head></html>"""
    assert viv.application_script_refs(html) == [
        "/assets/classic.js",
        "./assets/index-abc.js",
    ]


def test_scan_rejects_mark_only_in_preload_or_modulepreload_asset():
    html_with_stale_entry = """<!doctype html><html><head>
    <link rel="modulepreload" href="/assets/vendor.js">
    <link rel="preload" as="script" href="/assets/preload.js">
    <script type="module" src="/assets/index-abc.js"></script>
    </head><body></body></html>"""
    scripts = {
        "/usr/share/nginx/html/assets/vendor.js": 'const mark="stoa-app-version:1.13.0";\n',
        "/usr/share/nginx/html/assets/preload.js": 'const mark="stoa-app-version:1.13.0";\n',
        JS_PATH: 'const mark="stoa-app-version:2.0.0";\n',
    }
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(html_with_stale_entry, scripts, "1.13.0")

    html_preload_only = """<!doctype html><html><head>
    <link rel="modulepreload" href="/assets/vendor.js">
    <link rel="preload" as="script" href="/assets/preload.js">
    </head><body></body></html>"""
    with pytest.raises(viv.VersionMismatch, match="does not load any application JavaScript"):
        viv.scan_application_scripts_for_mark(html_preload_only, scripts, "1.13.0")


def test_scan_rejects_script_src_inside_html_comment():
    commented_only = """<!doctype html><html><head>
    <!-- <script type="module" src="/assets/index-abc.js"></script> -->
    </head><body></body></html>"""
    scripts = {JS_PATH: 'const mark="stoa-app-version:1.13.0";\n'}
    with pytest.raises(viv.VersionMismatch, match="does not load any application JavaScript"):
        viv.scan_application_scripts_for_mark(commented_only, scripts, "1.13.0")

    commented_plus_stale = """<!doctype html><html><head>
    <!-- <script type="module" src="/assets/fresh.js"></script> -->
    <script type="module" src="/assets/index-abc.js"></script>
    </head><body></body></html>"""
    scripts_both = {
        "/usr/share/nginx/html/assets/fresh.js": 'const mark="stoa-app-version:1.13.0";\n',
        JS_PATH: 'const mark="stoa-app-version:2.0.0";\n',
    }
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(commented_plus_stale, scripts_both, "1.13.0")

    commented_meta = '<html><head><!-- <meta name="stoa-app-version" content="1.13.0" /> --></head></html>'
    with pytest.raises(viv.VersionMismatch, match="missing the stoa-app-version meta tag"):
        viv.extract_meta_app_version(commented_meta)


def test_scan_rejects_mark_only_in_js_comments_and_preserves_strings():
    line_comment = {JS_PATH: '// "stoa-app-version:1.13.0"\nconst version="2.0.0";\n'}
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(INDEX_HTML, line_comment, "1.13.0")

    block_comment = {JS_PATH: '/* "stoa-app-version:1.13.0" */ const version="2.0.0";\n'}
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(INDEX_HTML, block_comment, "1.13.0")

    template_expr_comment = {
        JS_PATH: 'const s = `https://example.com/${/* "stoa-app-version:1.13.0" */ 1}`;\n'
    }
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(INDEX_HTML, template_expr_comment, "1.13.0")

    # String literals and regexes containing // or /* must not hide a real mark on the same line.
    minified_with_url = {
        JS_PATH: (
            'const url="https://api.gostoa.dev/*x*/",re=/https?:\\/\\//;'
            'const mark="stoa-app-version:1.13.0";'
        )
    }
    assert (
        viv.scan_application_scripts_for_mark(INDEX_HTML, minified_with_url, "1.13.0")
        == "stoa-app-version:1.13.0"
    )


def test_delimited_app_mark_rejects_prerelease_prefix_and_unquoted_partial():
    assert viv.has_delimited_app_mark('"stoa-app-version:1.13.0"', "1.13.0")
    assert not viv.has_delimited_app_mark('"stoa-app-version:1.13.0-rc.1"', "1.13.0")
    assert not viv.has_delimited_app_mark("stoa-app-version:1.13.0-rc.1", "1.13.0")
    assert viv.has_delimited_app_mark("mark=stoa-app-version:1.13.0;", "1.13.0")
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(
            INDEX_HTML,
            {JS_PATH: 'const mark="stoa-app-version:1.13.0-rc.1";\n'},
            "1.13.0",
        )


def test_frontends_derive_displayed_version_from_verified_mark():
    for rel in ("portal/src/config.ts", "control-plane-ui/src/config.ts"):
        text = (ROOT / rel).read_text()
        assert "appVersionFromMark(APP_VERSION_MARK" in text, rel
    for rel in (
        "portal/src/components/layout/Footer.tsx",
        "portal/src/components/layout/Sidebar.tsx",
        "control-plane-ui/src/components/Layout.tsx",
    ):
        text = (ROOT / rel).read_text()
        assert "data-stoa-app-version-mark={config.app.versionMark}" in text, rel
        assert "config.app.versionMark" in text and "stoa-app-version:" in text, rel


def test_scan_rejects_mark_only_in_unreferenced_html():
    index_html = INDEX_HTML
    scripts = {JS_PATH: 'export const version="2.0.0";\n'}
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(index_html, scripts, "1.13.0")
    leftover = {
        JS_PATH: 'export const version="2.0.0";\n',
        "/usr/share/nginx/html/unused.html": '<meta name="stoa-app-version" content="1.13.0" />'
        '<!-- stoa-app-version:1.13.0 -->',
    }
    with pytest.raises(viv.VersionMismatch, match="was not found in JavaScript loaded"):
        viv.scan_application_scripts_for_mark(index_html, leftover, "1.13.0")


def test_scan_accepts_quoted_mark_in_loaded_javascript():
    scripts = {JS_PATH: 'const mark="stoa-app-version:1.13.0";\n'}
    assert (
        viv.scan_application_scripts_for_mark(INDEX_HTML, scripts, "1.13.0")
        == "stoa-app-version:1.13.0"
    )


def test_vite_configs_define_a_complete_mark_literal():
    needle = "JSON.stringify(`stoa-app-version:${appVersion}`)"
    for rel in ("portal/vite.config.ts", "control-plane-ui/vite.config.ts"):
        text = (ROOT / rel).read_text()
        assert needle in text, rel
        assert "import.meta.env.VITE_APP_VERSION_MARK" in text, rel


def test_verify_frontend_stale_app_mark_fails_when_version_txt_is_correct():
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok("/usr/share/nginx/html/index.html", INDEX_HTML),
        _frontend_file_ok(JS_PATH, 'const mark="stoa-app-version:2.0.0";\n'),
    ])
    with pytest.raises(viv.VersionMismatch, match="application mark 'stoa-app-version:1.13.0'"):
        viv.verify_image_version("control-plane-ui", "1.13.0", "img:tag", runner=runner)
    assert not any(call[:2] == ["docker", "run"] and "-d" in call for call in runner.calls)


def test_verify_frontend_rejects_prerelease_prefix_in_loaded_javascript():
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok("/usr/share/nginx/html/index.html", INDEX_HTML),
        _frontend_file_ok(JS_PATH, 'const mark="stoa-app-version:1.13.0-rc.1";\n'),
    ])
    with pytest.raises(viv.VersionMismatch, match="application mark 'stoa-app-version:1.13.0'"):
        viv.verify_image_version("control-plane-ui", "1.13.0", "img:tag", runner=runner)


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


def test_verify_frontend_success_checks_vite_artifacts_before_server():
    inspect_payload = json.dumps([
        {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}}}
    ])
    runner = FakeRunner([
        _frontend_file_ok("/usr/share/nginx/html/version.txt", "1.13.0\n"),
        _frontend_file_ok("/usr/share/nginx/html/index.html", INDEX_HTML),
        _frontend_file_ok(JS_PATH, 'const mark="stoa-app-version:1.13.0";\n'),
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
