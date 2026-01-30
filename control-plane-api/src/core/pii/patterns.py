"""PII Detection Patterns — RGPD Art. 4"""
import re
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Pattern


class PIIType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    PHONE_FR = "phone_fr"
    IBAN = "iban"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    JWT = "jwt"
    API_KEY = "api_key"
    SSN_FR = "ssn_fr"


@dataclass(frozen=True)
class PIIPattern:
    pii_type: PIIType
    pattern: Pattern[str]
    mask_func: Callable[[str], str]
    priority: int = 0


class PIIPatterns:
    @staticmethod
    def mask_email(v: str) -> str:
        if "@" not in v:
            return "***@***.***"
        local, domain = v.rsplit("@", 1)
        parts = domain.split(".")
        return f"{local[0]}***@{parts[0][0]}***.{parts[-1]}"

    @staticmethod
    def mask_phone(v: str) -> str:
        digits = re.sub(r'\D', '', v)
        if len(digits) < 4:
            return "*" * len(v)
        prefix = v[:3] if v.startswith('+') else ""
        return f"{prefix}*****{digits[-4:]}"

    @staticmethod
    def mask_iban(v: str) -> str:
        clean = re.sub(r'\s', '', v)
        return f"{clean[:4]}****{clean[-4:]}" if len(clean) >= 8 else "*" * len(clean)

    @staticmethod
    def mask_cc(v: str) -> str:
        digits = re.sub(r'\D', '', v)
        return f"{digits[:4]}****{digits[-4:]}" if len(digits) >= 8 else "*" * len(v)

    @staticmethod
    def mask_ip(v: str) -> str:
        parts = v.split(".")
        return f"{parts[0]}.{parts[1]}.xxx.xxx" if len(parts) == 4 else v

    @staticmethod
    def mask_jwt(v: str) -> str:
        return "[JWT:REDACTED]"

    @staticmethod
    def mask_api_key(v: str) -> str:
        m = re.match(r'^([a-zA-Z]{2,4}[-_])', v)
        return f"{m.group(1)}***" if m else f"{v[:3]}***"

    @staticmethod
    def mask_full(v: str) -> str:
        return "*" * min(len(v), 8)

    _PATTERNS: list[PIIPattern] = [
        PIIPattern(PIIType.JWT, re.compile(r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*'), mask_jwt.__func__, 100),
        PIIPattern(PIIType.IBAN, re.compile(r'[A-Z]{2}\d{2}[A-Z0-9]{4,30}', re.I), mask_iban.__func__, 90),
        PIIPattern(PIIType.CREDIT_CARD, re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b'), mask_cc.__func__, 85),
        PIIPattern(PIIType.SSN_FR, re.compile(r'\b[12]\d{2}(?:0[1-9]|1[0-2])\d{5}\d{3}(?:\s?\d{2})?\b'), mask_full.__func__, 80),
        PIIPattern(PIIType.API_KEY, re.compile(r'\b(?:sk|pk|api|key|token|secret)[-_]?[A-Za-z0-9]{16,}\b', re.I), mask_api_key.__func__, 75),
        PIIPattern(PIIType.EMAIL, re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), mask_email.__func__, 70),
        PIIPattern(PIIType.PHONE_FR, re.compile(r'(?:\+33|0033|0)[1-9](?:[\s.-]?\d{2}){4}\b'), mask_phone.__func__, 65),
        PIIPattern(PIIType.PHONE, re.compile(r'\+?\d{1,4}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}\b'), mask_phone.__func__, 60),
        PIIPattern(PIIType.IP_ADDRESS, re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'), mask_ip.__func__, 50),
    ]

    @classmethod
    def get_all(cls) -> list[PIIPattern]:
        return sorted(cls._PATTERNS, key=lambda p: p.priority, reverse=True)

    @classmethod
    def get_enabled(cls, disabled: set[PIIType] | None = None) -> list[PIIPattern]:
        d = disabled or set()
        return [p for p in cls.get_all() if p.pii_type not in d]
