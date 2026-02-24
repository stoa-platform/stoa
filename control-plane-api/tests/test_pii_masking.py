"""Comprehensive PII masking tests — engine + middleware + admin (CAB-430).

Covers:
- PIIMasker: mask(), mask_dict(), detect_only(), config presets
- MaskingContext: exemptions, strict mode
- PIIMaskingMiddleware: query-string, headers, client IP masking
- PII Admin router: scan, mask, config endpoints + RBAC
"""

import pytest

from src.core.pii import (
    FieldMaskingMode,
    MaskingContext,
    MaskingLevel,
    PIIMasker,
    PIIMaskingConfig,
    PIIType,
    get_masker,
    mask_pii,
)

# ── PIIMasker Core ───────────────────────────────────────────────────────


class TestPIIMaskerMask:
    """PIIMasker.mask() — single string masking."""

    def test_masks_email(self):
        masker = PIIMasker()
        result = masker.mask("Contact john.doe@example.com for info")
        assert "john.doe@example.com" not in result
        assert "***" in result

    def test_masks_phone_fr(self):
        masker = PIIMasker()
        result = masker.mask("Call +33612345678 now")
        assert "+33612345678" not in result
        assert "5678" in result  # last 4 digits preserved

    def test_masks_iban(self):
        masker = PIIMasker()
        result = masker.mask("IBAN: FR7612345678901234567890123")
        assert "FR7612345678901234567890123" not in result
        assert result.startswith("IBAN: FR76")

    def test_masks_credit_card(self):
        masker = PIIMasker()
        result = masker.mask("Card: 4111111111111111")
        assert "4111111111111111" not in result
        assert "4111" in result  # first 4 preserved

    def test_masks_jwt(self):
        masker = PIIMasker()
        token = "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        result = masker.mask(token)
        assert "eyJ" not in result
        assert "[JWT:REDACTED]" in result

    def test_masks_ip_address(self):
        masker = PIIMasker()
        # Disable phone pattern so IP pattern is exercised directly
        config = PIIMaskingConfig(disabled_types={PIIType.PHONE, PIIType.PHONE_FR})
        masker = PIIMasker(config)
        result = masker.mask("Client IP: 192.168.1.42")
        assert "192.168.1.42" not in result
        assert "192.168.xxx.xxx" in result

    def test_masks_api_key(self):
        masker = PIIMasker()
        result = masker.mask("Key: sk_test_1234567890abcdef1234")
        assert "sk_test_1234567890abcdef1234" not in result
        assert "sk_" in result

    def test_no_pii_unchanged(self):
        masker = PIIMasker()
        text = "Hello world, no PII here"
        assert masker.mask(text) == text

    def test_disabled_returns_original(self):
        config = PIIMaskingConfig.development()
        masker = PIIMasker(config)
        text = "Email: john@example.com"
        assert masker.mask(text) == text

    def test_truncates_long_text(self):
        config = PIIMaskingConfig(max_text_length=50)
        masker = PIIMasker(config)
        long_text = "a" * 100 + " john@example.com"
        result = masker.mask(long_text)
        # Text truncated before email, so email not found
        assert len(result) <= 50

    def test_multiple_pii_types(self):
        masker = PIIMasker()
        text = "Email john@test.com, IP 10.0.0.1, phone +33612345678"
        result = masker.mask(text)
        assert "john@test.com" not in result
        assert "10.0.0.1" not in result
        assert "+33612345678" not in result


class TestPIIMaskerMaskDict:
    """PIIMasker.mask_dict() — recursive dict/list masking."""

    def test_masks_string_values(self):
        masker = PIIMasker()
        data = {"email": "john@example.com", "name": "John"}
        result = masker.mask_dict(data)
        assert "john@example.com" not in result["email"]
        assert result["name"] == "John"

    def test_recursive_nested_dict(self):
        masker = PIIMasker()
        data = {"user": {"contact": {"email": "jane@test.com"}}}
        result = masker.mask_dict(data)
        assert "jane@test.com" not in result["user"]["contact"]["email"]

    def test_masks_list_items(self):
        masker = PIIMasker()
        data = {"emails": ["a@test.com", "b@test.com"]}
        result = masker.mask_dict(data)
        assert all("@test.com" not in e for e in result["emails"])

    def test_non_recursive_mode(self):
        masker = PIIMasker()
        data = {"nested": {"email": "a@test.com"}}
        result = masker.mask_dict(data, recursive=False)
        # Non-recursive: nested dict values are NOT masked
        assert result["nested"]["email"] == "a@test.com"

    def test_preserves_non_string_values(self):
        masker = PIIMasker()
        data = {"count": 42, "active": True, "score": 3.14, "empty": None}
        result = masker.mask_dict(data)
        assert result == data

    def test_disabled_returns_original(self):
        config = PIIMaskingConfig.development()
        masker = PIIMasker(config)
        data = {"email": "john@example.com"}
        assert masker.mask_dict(data) == data


class TestPIIMaskerDetectOnly:
    """PIIMasker.detect_only() — returns unmasked values for debug."""

    def test_detects_email(self):
        masker = PIIMasker()
        result = masker.detect_only("Contact john@example.com")
        assert PIIType.EMAIL in result
        assert "john@example.com" in result[PIIType.EMAIL]

    def test_detects_multiple_types(self):
        masker = PIIMasker()
        result = masker.detect_only("john@test.com from 10.0.0.1")
        assert PIIType.EMAIL in result
        assert PIIType.IP_ADDRESS in result

    def test_empty_for_no_pii(self):
        masker = PIIMasker()
        result = masker.detect_only("Hello world")
        assert result == {}


# ── MaskingContext ───────────────────────────────────────────────────────


class TestMaskingContext:
    """MaskingContext exemption logic."""

    def test_exempt_role(self):
        config = PIIMaskingConfig(exempt_roles={"platform_admin"})
        ctx = MaskingContext(user_roles={"platform_admin"})
        assert ctx.is_exempt(config) is True

    def test_non_exempt_role(self):
        config = PIIMaskingConfig(exempt_roles={"platform_admin"})
        ctx = MaskingContext(user_roles={"viewer"})
        assert ctx.is_exempt(config) is False

    def test_strict_overrides_exemption(self):
        config = PIIMaskingConfig.strict()
        ctx = MaskingContext(user_roles={"platform_admin"})
        # Strict mode: nobody is exempt
        assert ctx.is_exempt(config) is False

    def test_empty_roles_not_exempt(self):
        config = PIIMaskingConfig()
        ctx = MaskingContext(user_roles=set())
        assert ctx.is_exempt(config) is False

    def test_exempt_user_skips_masking(self):
        config = PIIMaskingConfig(exempt_roles={"platform_admin"})
        masker = PIIMasker(config)
        ctx = MaskingContext(user_roles={"platform_admin"})
        text = "john@example.com"
        assert masker.mask(text, ctx) == text

    def test_strict_masks_even_exempt(self):
        config = PIIMaskingConfig.strict()
        masker = PIIMasker(config)
        ctx = MaskingContext(user_roles={"platform_admin"})
        text = "john@example.com"
        assert masker.mask(text, ctx) != text


# ── Config Presets ───────────────────────────────────────────────────────


class TestPIIMaskingConfig:
    """PIIMaskingConfig factory methods."""

    def test_strict(self):
        config = PIIMaskingConfig.strict()
        assert config.level == MaskingLevel.STRICT
        assert config.exempt_roles == set()

    def test_development(self):
        config = PIIMaskingConfig.development()
        assert config.enabled is False
        assert config.level == MaskingLevel.DISABLED

    def test_default_production(self):
        config = PIIMaskingConfig.default_production()
        assert config.enabled is True
        assert config.level == MaskingLevel.MODERATE
        assert "platform_admin" in config.exempt_roles

    def test_field_override_full(self):
        config = PIIMaskingConfig(field_overrides={PIIType.EMAIL: FieldMaskingMode.FULL})
        masker = PIIMasker(config)
        result = masker.mask("john@example.com")
        # FULL mode: entire match replaced with asterisks
        assert "@" not in result
        assert "***" in result

    def test_field_override_hash(self):
        config = PIIMaskingConfig(field_overrides={PIIType.EMAIL: FieldMaskingMode.HASH})
        masker = PIIMasker(config)
        result = masker.mask("john@example.com")
        assert "[HASH:" in result

    def test_field_override_none(self):
        config = PIIMaskingConfig(field_overrides={PIIType.EMAIL: FieldMaskingMode.NONE})
        masker = PIIMasker(config)
        text = "john@example.com"
        result = masker.mask(text)
        assert "john@example.com" in result

    def test_disabled_types(self):
        config = PIIMaskingConfig(disabled_types={PIIType.EMAIL})
        masker = PIIMasker(config)
        text = "john@example.com"
        # Email detection disabled — text unchanged
        assert masker.mask(text) == text


# ── Module-Level Helpers ─────────────────────────────────────────────────


class TestModuleHelpers:
    """get_masker() and mask_pii() convenience functions."""

    def test_get_masker_singleton(self):
        m1 = get_masker()
        m2 = get_masker()
        assert m1 is m2

    def test_mask_pii_convenience(self):
        result = mask_pii("john@example.com")
        assert "john@example.com" not in result

    def test_for_tenant_returns_masker(self):
        masker = PIIMasker.for_tenant("acme")
        assert isinstance(masker, PIIMasker)


# ── PII Masking Middleware ───────────────────────────────────────────────


class TestPIIMaskingMiddleware:
    """PIIMaskingMiddleware — ASGI scope masking."""

    @pytest.fixture(autouse=True)
    def _restore_mask_query_string(self):
        """Restore original _mask_query_string so middleware unit tests work."""
        from tests.conftest import _ORIGINAL_MASK_QUERY_STRING

        from src.middleware.pii_masking import PIIMaskingMiddleware

        PIIMaskingMiddleware._mask_query_string = _ORIGINAL_MASK_QUERY_STRING
        yield
        PIIMaskingMiddleware._mask_query_string = lambda _self, qs: qs

    def _make_scope(self, **kwargs):
        defaults = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "client": ("192.168.1.42", 12345),
        }
        defaults.update(kwargs)
        return defaults

    @pytest.mark.asyncio
    async def test_masks_client_ip(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = self._make_scope()
        await mw(scope, None, None)

        ip, port = captured_scope["client"]
        assert ip == "192.168.xxx.xxx"
        assert port == 12345

    @pytest.mark.asyncio
    async def test_masks_sensitive_headers(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = self._make_scope(
            headers=[
                (b"authorization", b"Bearer secret-token"),
                (b"x-api-key", b"sk_live_123456"),
                (b"content-type", b"application/json"),
            ]
        )
        await mw(scope, None, None)

        headers = dict(captured_scope["headers"])
        assert headers[b"authorization"] == b"[REDACTED]"
        assert headers[b"x-api-key"] == b"[REDACTED]"
        assert headers[b"content-type"] == b"application/json"

    @pytest.mark.asyncio
    async def test_masks_sensitive_query_params(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = self._make_scope(query_string=b"token=secret123&page=1")
        await mw(scope, None, None)

        qs = captured_scope["query_string"].decode()
        assert "secret123" not in qs
        assert "token=[REDACTED]" in qs
        assert "page=1" in qs

    @pytest.mark.asyncio
    async def test_masks_pii_in_query_values(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = self._make_scope(query_string=b"search=john@example.com&page=1")
        await mw(scope, None, None)

        qs = captured_scope["query_string"].decode()
        assert "john@example.com" not in qs
        assert "page=1" in qs

    @pytest.mark.asyncio
    async def test_disabled_passes_through(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app, enabled=False)
        scope = self._make_scope(query_string=b"token=secret123")
        await mw(scope, None, None)

        qs = captured_scope["query_string"].decode()
        assert "secret123" in qs  # Not masked when disabled

    @pytest.mark.asyncio
    async def test_skips_non_http(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = {"type": "websocket", "client": ("1.2.3.4", 80)}
        await mw(scope, None, None)

        # Client IP not masked for non-HTTP
        assert captured_scope["client"] == ("1.2.3.4", 80)

    @pytest.mark.asyncio
    async def test_empty_query_string(self):
        from src.middleware.pii_masking import PIIMaskingMiddleware

        captured_scope = {}

        async def app(scope, receive, send):
            captured_scope.update(scope)

        mw = PIIMaskingMiddleware(app)
        scope = self._make_scope(query_string=b"")
        await mw(scope, None, None)

        assert captured_scope["query_string"] == b""


# ── PII Admin Router ────────────────────────────────────────────────────


class TestPIIAdminScan:
    """POST /v1/admin/pii/scan"""

    def test_scan_detects_email(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.post(
            "/v1/admin/pii/scan",
            json={"text": "Contact john@example.com for details"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_pii_count"] >= 1
        types = [d["pii_type"] for d in body["detections"]]
        assert "email" in types

    def test_scan_detects_multiple(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.post(
            "/v1/admin/pii/scan",
            json={"text": "john@test.com from 10.0.0.1 with card 4111111111111111"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_pii_count"] >= 3

    def test_scan_no_pii(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.post(
            "/v1/admin/pii/scan",
            json={"text": "Hello world, nothing sensitive here"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_pii_count"] == 0
        assert body["detections"] == []

    def test_scan_forbidden_non_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.post(
            "/v1/admin/pii/scan",
            json={"text": "john@example.com"},
        )
        assert resp.status_code == 403


class TestPIIAdminMask:
    """POST /v1/admin/pii/mask"""

    def test_mask_replaces_email(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.post(
            "/v1/admin/pii/mask",
            json={"text": "Contact john@example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "john@example.com" not in body["masked_text"]
        assert body["original_length"] > 0

    def test_mask_forbidden_non_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.post(
            "/v1/admin/pii/mask",
            json={"text": "john@example.com"},
        )
        assert resp.status_code == 403


class TestPIIAdminConfig:
    """GET /v1/admin/pii/config"""

    def test_get_config(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.get("/v1/admin/pii/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["level"] == "moderate"
        assert "email" in body["pii_types"]
        assert isinstance(body["pii_types"], list)
        assert len(body["pii_types"]) == 9  # All PIIType values

    def test_config_forbidden_non_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/admin/pii/config")
        assert resp.status_code == 403
