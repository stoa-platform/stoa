"""PII Detection Patterns — RGPD Art. 4"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from re import Pattern


class PIIType(StrEnum):
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


def _mask_email(v: str) -> str:
    if "@" not in v:
        return "***@***.***"
    local, domain = v.rsplit("@", 1)
    parts = domain.split(".")
    return f"{local[0]}***@{parts[0][0]}***.{parts[-1]}"


def _mask_phone(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) < 4:
        return "*" * len(v)
    prefix = v[:3] if v.startswith("+") else ""
    return f"{prefix}*****{digits[-4:]}"


def _mask_iban(v: str) -> str:
    clean = re.sub(r"\s", "", v)
    return f"{clean[:4]}****{clean[-4:]}" if len(clean) >= 8 else "*" * len(clean)


def _mask_cc(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    return f"{digits[:4]}****{digits[-4:]}" if len(digits) >= 8 else "*" * len(v)


def _mask_ip(v: str) -> str:
    parts = v.split(".")
    return f"{parts[0]}.{parts[1]}.xxx.xxx" if len(parts) == 4 else v


def _mask_jwt(v: str) -> str:
    return "[JWT:REDACTED]"


def _mask_api_key(v: str) -> str:
    m = re.match(r"^([a-zA-Z]{2,4}[-_])", v)
    return f"{m.group(1)}***" if m else f"{v[:3]}***"


def _mask_full(v: str) -> str:
    return "*" * min(len(v), 8)


class PIIPatterns:
    _PATTERNS: list[PIIPattern] = [
        PIIPattern(PIIType.JWT, re.compile(r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*"), _mask_jwt, 100),
        PIIPattern(PIIType.IBAN, re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{4,30}", re.I), _mask_iban, 90),
        PIIPattern(
            PIIType.CREDIT_CARD,
            re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b"),
            _mask_cc,
            85,
        ),
        PIIPattern(
            PIIType.SSN_FR, re.compile(r"\b[12]\d{2}(?:0[1-9]|1[0-2])\d{5}\d{3}(?:\s?\d{2})?\b"), _mask_full, 80
        ),
        PIIPattern(
            PIIType.API_KEY,
            re.compile(r"\b(?:sk|pk|api|key|token|secret)[-_]?[A-Za-z0-9]{16,}\b", re.I),
            _mask_api_key,
            75,
        ),
        PIIPattern(PIIType.EMAIL, re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), _mask_email, 70),
        PIIPattern(PIIType.PHONE_FR, re.compile(r"(?:\+33|0033|0)[1-9](?:[\s.-]?\d{2}){4}\b"), _mask_phone, 65),
        PIIPattern(
            PIIType.PHONE, re.compile(r"\+?\d{1,4}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}\b"), _mask_phone, 60
        ),
        PIIPattern(
            PIIType.IP_ADDRESS,
            re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
            _mask_ip,
            50,
        ),
    ]

    # Keep static methods as public API aliases
    mask_email = staticmethod(_mask_email)
    mask_phone = staticmethod(_mask_phone)
    mask_iban = staticmethod(_mask_iban)
    mask_cc = staticmethod(_mask_cc)
    mask_ip = staticmethod(_mask_ip)
    mask_jwt = staticmethod(_mask_jwt)
    mask_api_key = staticmethod(_mask_api_key)
    mask_full = staticmethod(_mask_full)

    @classmethod
    def get_all(cls) -> list[PIIPattern]:
        return sorted(cls._PATTERNS, key=lambda p: p.priority, reverse=True)

    @classmethod
    def get_enabled(cls, disabled: set[PIIType] | None = None) -> list[PIIPattern]:
        d = disabled or set()
        return [p for p in cls.get_all() if p.pii_type not in d]
