"""Tests for RFC 8705 Certificate Binding Validation Middleware (CAB-868)."""

import base64
import json
import time

import pytest

from src.middleware.cert_binding import CertBindingMiddleware, _decode_jwt_payload


# =============================================================================
# Helpers
# =============================================================================


def _b64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_jwt(payload: dict, header: dict | None = None) -> str:
    """Create a fake JWT (unsigned) with the given payload."""
    if header is None:
        header = {"alg": "RS256", "kid": "test-key-1"}
    h = _b64url_encode(json.dumps(header).encode())
    p = _b64url_encode(json.dumps(payload).encode())
    s = _b64url_encode(b"fakesignature")
    return f"{h}.{p}.{s}"


FINGERPRINT = "dGVzdC1maW5nZXJwcmludC1zaGEyNTYtYmFzZTY0dXJs"
FINGERPRINT_UPPER = FINGERPRINT.upper()

SAMPLE_PAYLOAD = {
    "sub": "client-123",
    "iss": "https://auth.gostoa.dev/realms/stoa",
    "aud": "stoa-mcp-gateway",
    "exp": int(time.time()) + 3600,
    "cnf": {"x5t#S256": FINGERPRINT},
}

PAYLOAD_NO_CNF = {
    "sub": "client-456",
    "iss": "https://auth.gostoa.dev/realms/stoa",
    "exp": int(time.time()) + 3600,
}


# =============================================================================
# Unit tests for _decode_jwt_payload
# =============================================================================


class TestDecodeJwtPayload:
    def test_valid_jwt(self):
        token = _make_jwt(SAMPLE_PAYLOAD)
        result = _decode_jwt_payload(token)
        assert result is not None
        assert result["sub"] == "client-123"
        assert result["cnf"]["x5t#S256"] == FINGERPRINT

    def test_invalid_token_format(self):
        assert _decode_jwt_payload("not-a-jwt") is None

    def test_invalid_base64(self):
        assert _decode_jwt_payload("a.!!!invalid!!!.c") is None

    def test_empty_string(self):
        assert _decode_jwt_payload("") is None


# =============================================================================
# Unit tests for CertBindingMiddleware logic
# =============================================================================


class TestCertBindingValidation:
    """Tests for the core validation logic extracted from the middleware."""

    def test_timing_safe_comparison_match(self):
        """Matching fingerprints should pass (case-insensitive)."""
        import secrets

        a = FINGERPRINT.lower().encode("ascii")
        b = FINGERPRINT_UPPER.lower().encode("ascii")
        assert secrets.compare_digest(a, b)

    def test_timing_safe_comparison_mismatch(self):
        """Mismatched fingerprints should fail."""
        import secrets

        a = FINGERPRINT.lower().encode("ascii")
        b = b"wrong-fingerprint"
        assert not secrets.compare_digest(a, b)

    def test_case_insensitive_comparison(self):
        """Base64url fingerprints should be compared case-insensitively."""
        import secrets

        a = "AbCdEf123".lower().encode("ascii")
        b = "abcdef123".lower().encode("ascii")
        assert secrets.compare_digest(a, b)


# =============================================================================
# Integration-style tests using ASGI app
# =============================================================================


@pytest.fixture
def _enable_cert_binding(monkeypatch):
    """Enable cert binding for tests."""
    monkeypatch.setenv("CERT_BINDING_ENABLED", "true")
    monkeypatch.setenv("CERT_BINDING_HEADER", "X-SSL-Client-Cert-SHA256")
    from src.config import clear_settings_cache
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def _disable_cert_binding(monkeypatch):
    """Disable cert binding for tests."""
    monkeypatch.setenv("CERT_BINDING_ENABLED", "false")
    from src.config import clear_settings_cache
    clear_settings_cache()
    yield
    clear_settings_cache()


class TestCertBindingMiddlewareIntegration:
    """Test the middleware dispatch logic via a minimal ASGI app."""

    @pytest.fixture
    def app(self, _enable_cert_binding):
        """Create a minimal FastAPI app with CertBindingMiddleware."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        app = FastAPI()
        app.add_middleware(CertBindingMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return JSONResponse({"status": "ok"})

        @app.get("/health/ready")
        async def health():
            return JSONResponse({"status": "healthy"})

        return app

    @pytest.fixture
    def client(self, app):
        from starlette.testclient import TestClient
        return TestClient(app, raise_server_exceptions=False)

    def test_valid_cert_matching_header(self, client):
        """Valid JWT with cnf + matching header → 200."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        resp = client.get(
            "/test",
            headers={
                "Authorization": f"Bearer {token}",
                "X-SSL-Client-Cert-SHA256": FINGERPRINT,
            },
        )
        assert resp.status_code == 200

    def test_valid_cert_case_insensitive(self, client):
        """Fingerprint comparison should be case-insensitive."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        resp = client.get(
            "/test",
            headers={
                "Authorization": f"Bearer {token}",
                "X-SSL-Client-Cert-SHA256": FINGERPRINT_UPPER,
            },
        )
        assert resp.status_code == 200

    def test_cnf_present_header_missing_rejects(self, client):
        """JWT with cnf but no fingerprint header → 401 (strict mode)."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        resp = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "invalid_token"
        assert "header missing" in body["error_description"]

    def test_fingerprint_mismatch_rejects(self, client):
        """JWT with cnf + wrong fingerprint header → 401."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        resp = client.get(
            "/test",
            headers={
                "Authorization": f"Bearer {token}",
                "X-SSL-Client-Cert-SHA256": "wrong-fingerprint-value",
            },
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "invalid_token"
        assert "validation failed" in body["error_description"]

    def test_no_cnf_allows_through(self, client):
        """JWT without cnf claim → allow (client_secret flow)."""
        token = _make_jwt(PAYLOAD_NO_CNF)
        resp = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_no_auth_header_passes_through(self, client):
        """No Authorization header → passes through to auth middleware."""
        resp = client.get("/test")
        assert resp.status_code == 200  # No auth = middleware doesn't block

    def test_exempt_path_bypasses_validation(self, client):
        """Health endpoints bypass cert binding."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        # cnf present but no fingerprint header — would normally reject,
        # but /health is exempt
        resp = client.get(
            "/health/ready",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_invalid_cnf_missing_x5t(self, client):
        """cnf claim without x5t#S256 → 401."""
        payload = {**PAYLOAD_NO_CNF, "cnf": {"other": "value"}}
        token = _make_jwt(payload)
        resp = client.get(
            "/test",
            headers={
                "Authorization": f"Bearer {token}",
                "X-SSL-Client-Cert-SHA256": FINGERPRINT,
            },
        )
        assert resp.status_code == 401
        assert "x5t#S256" in resp.json()["error_description"]


class TestCertBindingDisabled:
    """Tests when feature flag is off."""

    @pytest.fixture
    def app(self, _disable_cert_binding):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        app = FastAPI()
        app.add_middleware(CertBindingMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return JSONResponse({"status": "ok"})

        return app

    @pytest.fixture
    def client(self, app):
        from starlette.testclient import TestClient
        return TestClient(app, raise_server_exceptions=False)

    def test_disabled_bypasses_all(self, client):
        """With feature flag off, cert-bound tokens pass without header."""
        token = _make_jwt(SAMPLE_PAYLOAD)
        resp = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
