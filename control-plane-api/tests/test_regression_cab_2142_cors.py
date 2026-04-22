"""Regression tests for CAB-2142 (Security MEGA CAB-2079 — CORS hardening).

Before the fix:
- `main.py:664-671` used `allow_methods=["*"]` and `allow_headers=["*"]`,
  expanding the CORS surface beyond the handful of methods/headers actually
  used by the Console and Portal.
- `CORS_ORIGINS` in prod carried `http://localhost:*` and `http://*.stoa.local`
  origins (dev leftovers), widening the cross-origin attack surface.

After the fix:
- `allow_methods` and `allow_headers` are explicit allow-lists.
- `settings.cors_origins_list` strips `localhost` and `*.stoa.local` when
  `ENVIRONMENT=production` (logged once at boot). Dev/staging keep them.
- Preflight `OPTIONS` from an unknown origin does not receive
  `Access-Control-Allow-Origin`; from a known origin it does.
"""

# regression for CAB-2079
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from src.main import ALLOWED_CORS_HEADERS, ALLOWED_CORS_METHODS


def _make_app(origins: list[str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_CORS_METHODS,
        allow_headers=ALLOWED_CORS_HEADERS,
    )

    @app.get("/probe")
    async def probe():
        return {"ok": True}

    return app


class TestAllowedListsAreExplicit:
    """`allow_methods` and `allow_headers` must never be `["*"]` again."""

    def test_methods_list_is_explicit(self):
        assert "*" not in ALLOWED_CORS_METHODS
        # Canonical verbs the API actually uses
        for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            assert verb in ALLOWED_CORS_METHODS

    def test_headers_list_is_explicit(self):
        assert "*" not in ALLOWED_CORS_HEADERS
        for header in (
            "Authorization",
            "Content-Type",
            "X-Tenant-Id",
            "X-Operator-Key",
            "X-Request-Id",
            "X-API-Key",
            "Traceparent",
        ):
            assert header in ALLOWED_CORS_HEADERS


class TestPreflight:
    """Preflight responses must respect the allow-lists."""

    ORIGIN = "https://console.test.example"

    @pytest.mark.asyncio
    async def test_allowed_origin_receives_acao(self):
        app = _make_app([self.ORIGIN])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.options(
                "/probe",
                headers={
                    "Origin": self.ORIGIN,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == self.ORIGIN
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "GET" in allow_methods
        # The wildcard must not leak back through the response headers
        assert "*" not in allow_methods

    @pytest.mark.asyncio
    async def test_disallowed_origin_gets_no_acao(self):
        app = _make_app([self.ORIGIN])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.options(
                "/probe",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
        # Starlette still returns 200 for unknown origins; the contract is that
        # no Access-Control-Allow-Origin header is emitted.
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}

    @pytest.mark.asyncio
    async def test_disallowed_method_not_echoed(self):
        """A pre-flight request that asks for a method outside the allow-list
        must not receive that method back in `Access-Control-Allow-Methods`."""
        app = _make_app([self.ORIGIN])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.options(
                "/probe",
                headers={
                    "Origin": self.ORIGIN,
                    "Access-Control-Request-Method": "TRACE",
                },
            )
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "TRACE" not in allow_methods


class TestProductionOriginsStripping:
    """`cors_origins_list` must drop localhost + *.stoa.local when
    `ENVIRONMENT=production`, and keep them otherwise."""

    def _settings(self, env: str):
        from src.config import Settings

        return Settings(
            ENVIRONMENT=env,
            CORS_ORIGINS=(
                "https://console.gostoa.dev,"
                "https://portal.gostoa.dev,"
                "http://localhost:3000,"
                "http://localhost:5173,"
                "http://console.stoa.local"
            ),
        )

    def test_production_strips_localhost_and_stoa_local(self):
        s = self._settings("production")
        origins = s.cors_origins_list
        assert "https://console.gostoa.dev" in origins
        assert "https://portal.gostoa.dev" in origins
        assert all("localhost" not in o for o in origins)
        assert all(".stoa.local" not in o for o in origins)

    def test_dev_keeps_localhost(self):
        s = self._settings("dev")
        origins = s.cors_origins_list
        assert "http://localhost:3000" in origins
        assert "http://console.stoa.local" in origins

    def test_staging_keeps_localhost(self):
        # Staging runs against real dev clusters; no reason to strip here.
        s = self._settings("staging")
        origins = s.cors_origins_list
        assert "http://localhost:3000" in origins
