"""Tests for PII detection patterns (CAB-1291)"""
import pytest

from src.core.pii.patterns import PIIPatterns, PIIType


class TestMaskEmail:
    def test_standard(self):
        result = PIIPatterns.mask_email("john.doe@example.com")
        assert result.startswith("j")
        assert "***" in result
        assert result.endswith("com")

    def test_no_at(self):
        result = PIIPatterns.mask_email("noemail")
        assert result == "***@***.***"


class TestMaskPhone:
    def test_international(self):
        result = PIIPatterns.mask_phone("+33612345678")
        assert result.endswith("5678")
        assert "*" in result

    def test_short(self):
        result = PIIPatterns.mask_phone("123")
        assert result == "***"

    def test_local(self):
        result = PIIPatterns.mask_phone("0612345678")
        assert result.endswith("5678")


class TestMaskIban:
    def test_standard(self):
        result = PIIPatterns.mask_iban("FR76 1234 5678 9012 3456 7890 123")
        assert result.startswith("FR76")
        assert result.endswith("0123")
        assert "****" in result

    def test_short(self):
        result = PIIPatterns.mask_iban("FR76")
        assert result == "****"


class TestMaskCreditCard:
    def test_visa(self):
        result = PIIPatterns.mask_cc("4111111111111111")
        assert result.startswith("4111")
        assert result.endswith("1111")

    def test_short(self):
        result = PIIPatterns.mask_cc("4111")
        assert "*" in result


class TestMaskIP:
    def test_ipv4(self):
        result = PIIPatterns.mask_ip("192.168.1.42")
        assert result == "192.168.xxx.xxx"

    def test_non_ipv4(self):
        result = PIIPatterns.mask_ip("not-an-ip")
        assert result == "not-an-ip"


class TestMaskJWT:
    def test_redact(self):
        assert PIIPatterns.mask_jwt("eyJhbGciOiJSUzI1NiJ9.xxx.yyy") == "[JWT:REDACTED]"


class TestMaskAPIKey:
    def test_with_prefix(self):
        result = PIIPatterns.mask_api_key("sk_test_1234567890abcdef")
        assert result.startswith("sk_")
        assert result.endswith("***")

    def test_no_prefix(self):
        result = PIIPatterns.mask_api_key("1234567890abcdef")
        assert result == "123***"


class TestMaskFull:
    def test_short(self):
        assert PIIPatterns.mask_full("abc") == "***"

    def test_long(self):
        assert PIIPatterns.mask_full("a" * 20) == "********"


class TestPatternDetection:
    def test_email_detected(self):
        patterns = PIIPatterns.get_all()
        email_pattern = next(p for p in patterns if p.pii_type == PIIType.EMAIL)
        assert email_pattern.pattern.search("user@example.com")

    def test_jwt_detected(self):
        patterns = PIIPatterns.get_all()
        jwt_pattern = next(p for p in patterns if p.pii_type == PIIType.JWT)
        token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        assert jwt_pattern.pattern.search(token)

    def test_ip_detected(self):
        patterns = PIIPatterns.get_all()
        ip_pattern = next(p for p in patterns if p.pii_type == PIIType.IP_ADDRESS)
        assert ip_pattern.pattern.search("192.168.1.1")

    def test_iban_detected(self):
        patterns = PIIPatterns.get_all()
        iban_pattern = next(p for p in patterns if p.pii_type == PIIType.IBAN)
        assert iban_pattern.pattern.search("FR7612345678901234567890123")


class TestGetAllAndEnabled:
    def test_get_all_sorted_by_priority(self):
        patterns = PIIPatterns.get_all()
        priorities = [p.priority for p in patterns]
        assert priorities == sorted(priorities, reverse=True)

    def test_get_enabled_filters(self):
        all_patterns = PIIPatterns.get_all()
        enabled = PIIPatterns.get_enabled(disabled={PIIType.EMAIL, PIIType.PHONE})
        assert len(enabled) < len(all_patterns)
        assert all(p.pii_type != PIIType.EMAIL for p in enabled)
        assert all(p.pii_type != PIIType.PHONE for p in enabled)

    def test_get_enabled_no_filter(self):
        all_patterns = PIIPatterns.get_all()
        enabled = PIIPatterns.get_enabled()
        assert len(enabled) == len(all_patterns)
