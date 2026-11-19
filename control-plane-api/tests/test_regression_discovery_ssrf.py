"""Regression: POST /v1/discovery/detect must not reach internal addresses (SSRF).

CodeQL py/full-ssrf (alert 1511): any authenticated user could make the
control plane fetch an arbitrary URL, redirects included, and read back parts
of the response.
"""

from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User, get_current_user
from src.routers import discovery
from src.services import outbound_url
from src.services.outbound_url import UnsafeOutboundURLError, ensure_public_http_url

PUBLIC_IP = "93.184.215.14"
DNS = {"public.example": [PUBLIC_IP], "internal.example": ["10.1.2.3"], "mixed.example": [PUBLIC_IP, "127.0.0.1"]}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in DNS:
            raise OSError("unknown host")
        return DNS[host]

    monkeypatch.setattr(outbound_url, "_resolve", resolve)


def probe_app(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> FastAPI:
    monkeypatch.setattr(discovery, "_PROBE_TRANSPORT", httpx.MockTransport(handler))
    app = FastAPI()
    app.include_router(discovery.router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1", email="u1@example.test", username="u1", roles=["viewer"], tenant_id="t1"
    )
    return app


async def detect(app: FastAPI, url: str) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://cp.invalid") as client:
        return await client.post("/v1/discovery/detect", json={"url": url})


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1:8200",
        "http://[::ffff:127.0.0.1]/",
        "http://100.64.0.1/",
        "http://internal.example",
        "http://mixed.example",
        "http://unknown.example",
        "file:///etc/passwd",
        "ftp://public.example/",
        "http://user:pass@public.example/",
    ],
)
async def test_regression_detect_refuses_non_public_targets(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        return httpx.Response(200, json={"openapi": "3.0.0", "info": {"title": "secret"}, "paths": {}})

    response = await detect(probe_app(monkeypatch, handler), url)

    assert response.status_code == 422
    assert fetched == []


async def test_regression_detect_does_not_follow_redirect_to_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://internal.example/openapi.json"})
        return httpx.Response(200, json={"openapi": "3.0.0", "info": {"title": "secret"}, "paths": {}})

    response = await detect(probe_app(monkeypatch, handler), "http://public.example")

    assert response.status_code == 422
    assert fetched and {httpx.URL(url).host for url in fetched} == {"public.example"}


async def test_detect_still_probes_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"openapi": "3.0.0", "info": {"title": "Pets"}, "paths": {"/p": {}}})
        return httpx.Response(404)

    response = await detect(probe_app(monkeypatch, handler), "https://public.example")

    assert response.status_code == 200
    assert response.json()["protocol"] == "openapi"
    assert response.json()["title"] == "Pets"


async def test_public_ip_literal_is_accepted() -> None:
    await ensure_public_http_url(f"https://{PUBLIC_IP}/openapi.json")


async def test_invalid_port_is_refused() -> None:
    with pytest.raises(UnsafeOutboundURLError):
        await ensure_public_http_url("http://public.example:99999/")
