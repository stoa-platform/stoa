"""Regression tests for CAB-2587.

Interactive docs (Swagger UI, ReDoc) need a Content-Security-Policy that
allows their CDN scripts and inline styles. That policy used to be attached
to every proxied ``/api/`` response. Application routes must keep the strict
policy, and the proxies must not put the docs policy back on the whole API.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.middleware.security_headers import (
    APPLICATION_CSP,
    INTERACTIVE_DOCS_CSP,
    SecurityHeadersMiddleware,
    content_security_policy_for_path,
    is_interactive_docs_path,
)

_OTHER_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "x-xss-protection": "0",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROXY_CONFIGS = (
    _REPO_ROOT / "control-plane-ui" / "nginx.conf.template",
    _REPO_ROOT / "deploy" / "docker-compose" / "config" / "nginx" / "nginx.conf",
)


def _assert_other_security_headers(headers) -> None:
    for name, value in _OTHER_SECURITY_HEADERS.items():
        assert headers[name] == value


def test_regression_cab_2587_application_policy_has_no_docs_allowances() -> None:
    """The application CSP must not gain the allowances Swagger/ReDoc need."""
    assert "unsafe-inline" not in APPLICATION_CSP
    assert "unsafe-eval" not in APPLICATION_CSP
    assert "cdn.jsdelivr.net" not in APPLICATION_CSP
    assert APPLICATION_CSP != INTERACTIVE_DOCS_CSP
    assert "https://cdn.jsdelivr.net" in INTERACTIVE_DOCS_CSP
    assert "'unsafe-inline'" in INTERACTIVE_DOCS_CSP
    assert "'unsafe-eval'" in INTERACTIVE_DOCS_CSP


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/health", APPLICATION_CSP),
        ("/", APPLICATION_CSP),
        ("/openapi.json", APPLICATION_CSP),
        ("/v1/docs", APPLICATION_CSP),
        ("/v1/docs/search", APPLICATION_CSP),
        ("/docs-search", APPLICATION_CSP),
        ("/redoc-extra", APPLICATION_CSP),
        ("/docs", INTERACTIVE_DOCS_CSP),
        ("/docs/", INTERACTIVE_DOCS_CSP),
        ("/docs/oauth2-redirect", INTERACTIVE_DOCS_CSP),
        ("/redoc", INTERACTIVE_DOCS_CSP),
        ("/redoc/", INTERACTIVE_DOCS_CSP),
    ],
)
def test_regression_cab_2587_csp_selection_by_path(path: str, expected: str) -> None:
    assert is_interactive_docs_path(path) == (expected == INTERACTIVE_DOCS_CSP)
    assert content_security_policy_for_path(path) == expected


@pytest.mark.asyncio
async def test_regression_cab_2587_middleware_splits_csp_and_sets_security_headers() -> None:
    """Header boundary: strict CSP on an app route, docs CSP on Swagger/ReDoc."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/docs")
    async def docs() -> dict[str, str]:
        return {"kind": "swagger"}

    @app.get("/redoc")
    async def redoc() -> dict[str, str]:
        return {"kind": "redoc"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        app_response = await client.get("/health")
        docs_response = await client.get("/docs")
        redoc_response = await client.get("/redoc")

    assert app_response.headers["content-security-policy"] == APPLICATION_CSP
    assert docs_response.headers["content-security-policy"] == INTERACTIVE_DOCS_CSP
    assert redoc_response.headers["content-security-policy"] == INTERACTIVE_DOCS_CSP
    for response in (app_response, docs_response, redoc_response):
        _assert_other_security_headers(response.headers)


def test_regression_cab_2587_application_route_keeps_strict_csp(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert csp == APPLICATION_CSP
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "cdn.jsdelivr.net" not in csp
    _assert_other_security_headers(response.headers)


def test_regression_cab_2587_openapi_and_docs_search_stay_strict(client) -> None:
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.headers["content-security-policy"] == APPLICATION_CSP

    # ``/v1/docs`` is the docs-search API. Whatever status it returns, it must
    # not inherit the interactive-docs policy.
    search = client.get("/v1/docs")
    assert search.headers["content-security-policy"] == APPLICATION_CSP
    _assert_other_security_headers(search.headers)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_regression_cab_2587_interactive_docs_use_dedicated_csp(client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert csp == INTERACTIVE_DOCS_CSP
    assert csp != APPLICATION_CSP
    assert "https://cdn.jsdelivr.net" in csp
    assert "'unsafe-inline'" in csp
    _assert_other_security_headers(response.headers)


def test_regression_cab_2587_unknown_route_keeps_strict_csp(client) -> None:
    response = client.get("/not-a-real-route")
    assert response.status_code == 404
    assert response.headers["content-security-policy"] == APPLICATION_CSP
    _assert_other_security_headers(response.headers)


@pytest.mark.parametrize("config_path", _PROXY_CONFIGS, ids=lambda path: path.name)
def test_regression_cab_2587_proxies_do_not_stamp_docs_csp_on_the_api(config_path: Path) -> None:
    """The console and compose proxies must not re-apply the docs CSP to /api/."""
    text = config_path.read_text(encoding="utf-8")
    assert "unsafe-eval" not in text
    assert "unsafe-inline" not in text
    assert "cdn.jsdelivr.net" not in text
