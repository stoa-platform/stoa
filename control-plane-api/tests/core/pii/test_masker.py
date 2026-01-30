import pytest
from src.core.pii import PIIMasker, MaskingContext, PIIMaskingConfig, PIIPatterns, PIIType, MaskingLevel


class TestPatterns:
    def test_email(self):
        assert "john" not in PIIPatterns.mask_email("john@example.com")

    def test_phone(self):
        assert PIIPatterns.mask_phone("+33612345678").endswith("5678")

    def test_iban(self):
        assert PIIPatterns.mask_iban("FR7630001007941234567890185") == "FR76****0185"

    def test_cc(self):
        assert PIIPatterns.mask_cc("4111111111111111") == "4111****1111"

    def test_ip(self):
        assert PIIPatterns.mask_ip("192.168.1.100") == "192.168.xxx.xxx"

    def test_jwt(self):
        assert PIIPatterns.mask_jwt("eyJhbGc...") == "[JWT:REDACTED]"


class TestMasker:
    @pytest.fixture
    def masker(self):
        return PIIMasker()

    def test_email_in_text(self, masker):
        assert "john@example.com" not in masker.mask("Contact: john@example.com")

    def test_multiple_pii(self, masker):
        result = masker.mask("Email john@test.com, phone +33612345678, IP 192.168.1.1")
        assert "john@test.com" not in result and "+33612345678" not in result

    def test_jwt_token(self, masker):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc123"
        assert "[JWT:REDACTED]" in masker.mask(f"Token: {jwt}")

    def test_disabled(self):
        m = PIIMasker(PIIMaskingConfig(enabled=False))
        assert m.mask("john@example.com") == "john@example.com"

    def test_exempt_role(self, masker):
        ctx = MaskingContext(user_roles={"platform_admin"})
        assert masker.mask("john@example.com", ctx) == "john@example.com"

    def test_strict_no_exempt(self):
        m = PIIMasker(PIIMaskingConfig.strict())
        ctx = MaskingContext(user_roles={"platform_admin"})
        assert "john@example.com" not in m.mask("john@example.com", ctx)

    def test_mask_dict(self, masker):
        data = {"email": "john@example.com", "nested": {"ip": "192.168.1.1"}}
        result = masker.mask_dict(data)
        assert "john@example.com" not in str(result)

    def test_performance(self, masker):
        import time
        text = "Log with user@test.com and 192.168.1.1\n" * 200
        start = time.perf_counter()
        masker.mask(text)
        assert time.perf_counter() - start < 0.1
