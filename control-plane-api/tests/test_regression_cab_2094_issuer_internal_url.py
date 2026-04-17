"""Regression tests for CAB-2094.

Before the fix:
- `KEYCLOAK_URL` was overloaded: used both for issuer validation and for
  backend-to-KC calls (admin API, JWKS fetch, token exchange).
- Prod set `KEYCLOAK_URL=http://keycloak.stoa-system.svc.cluster.local` so the
  backend could reach Keycloak without hairpin NAT, but Keycloak still embedded
  `iss=https://auth.gostoa.dev/realms/stoa` in every token — so
  `jwt.decode(issuer=expected_issuer)` rejected every real user token with
  "Invalid issuer".

After the fix:
- `KEYCLOAK_URL` is the public URL (authoritative for `iss` claims).
- `KEYCLOAK_INTERNAL_URL` is optional, used for backend-to-KC calls only.
- `settings.keycloak_internal_url` falls back to `KEYCLOAK_URL` when unset so
  local/dev setups keep working.
"""

from unittest.mock import patch

import httpx
import pytest

from src.auth.dependencies import (
    _clear_keycloak_public_key_cache,
    _kc_issuer_url,
    _kc_public_key_url,
    get_keycloak_public_key,
)
from src.config import Settings


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_keycloak_public_key_cache()
    yield
    _clear_keycloak_public_key_cache()


class TestKeycloakInternalUrlFallback:
    """`keycloak_internal_url` must fall back to `KEYCLOAK_URL` when unset."""

    def test_falls_back_to_public_when_empty(self):
        s = Settings(
            KEYCLOAK_URL="https://auth.gostoa.dev",
            KEYCLOAK_INTERNAL_URL="",
        )
        assert s.keycloak_internal_url == "https://auth.gostoa.dev"

    def test_prefers_internal_when_set(self):
        s = Settings(
            KEYCLOAK_URL="https://auth.gostoa.dev",
            KEYCLOAK_INTERNAL_URL="http://keycloak.stoa-system.svc.cluster.local",
        )
        assert s.keycloak_internal_url == "http://keycloak.stoa-system.svc.cluster.local"


class TestIssuerUsesPublicUrl:
    """`iss` match must use the public URL, even when internal URL is set."""

    def test_issuer_uses_public_url_even_when_internal_diverges(self):
        with patch("src.auth.dependencies.settings") as m:
            m.KEYCLOAK_URL = "https://auth.gostoa.dev"
            m.keycloak_internal_url = "http://keycloak.stoa-system.svc.cluster.local"
            m.KEYCLOAK_REALM = "stoa"
            assert _kc_issuer_url() == "https://auth.gostoa.dev/realms/stoa"

    def test_public_key_url_uses_internal_when_set(self):
        with patch("src.auth.dependencies.settings") as m:
            m.KEYCLOAK_URL = "https://auth.gostoa.dev"
            m.keycloak_internal_url = "http://keycloak.stoa-system.svc.cluster.local"
            m.KEYCLOAK_REALM = "stoa"
            assert _kc_public_key_url() == "http://keycloak.stoa-system.svc.cluster.local/realms/stoa"


class TestPublicKeyFetchHitsInternalUrl:
    """JWKS fetch must target the internal URL when configured."""

    @pytest.mark.asyncio
    async def test_fetch_targets_internal_url(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"public_key": "MIIBIj..."})

        transport = httpx.MockTransport(handler)

        class _FakeClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                super().__init__(*a, transport=transport, **kw)

        with (
            patch("src.auth.dependencies.httpx.AsyncClient", _FakeClient),
            patch("src.auth.dependencies.settings") as m,
        ):
            m.KEYCLOAK_URL = "https://auth.gostoa.dev"
            m.keycloak_internal_url = "http://keycloak.stoa-system.svc.cluster.local"
            m.KEYCLOAK_REALM = "stoa"
            await get_keycloak_public_key()

        assert captured["url"] == "http://keycloak.stoa-system.svc.cluster.local/realms/stoa"
