"""Redact secrets from logs and stored event metadata.

The raw API key and invite token must never be written to logs or returned
from list responses. This module is the single scrubber for both paths.
"""

import logging
import re

_API_KEY = re.compile(r"stoa_sk_[0-9a-fA-F]{8,}")
_BEARER = re.compile(r"(?i)(bearer\s+)\S+")
_WELCOME = re.compile(r"(/welcome/)[^/\s\"']+")

_SENSITIVE_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "access_token",
        "refresh_token",
    }
)


def scrub_text(value: str) -> str:
    """Remove API keys, bearer tokens, and welcome tokens from a string."""
    value = _API_KEY.sub("stoa_sk_[redacted]", value)
    value = _BEARER.sub(r"\1[redacted]", value)
    value = _WELCOME.sub(r"\1[redacted]", value)
    return value


def scrub_metadata(metadata: dict | None) -> dict:
    """Drop secret fields before they are stored or listed."""
    if not metadata:
        return {}
    cleaned: dict = {}
    for key, value in metadata.items():
        if str(key).lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, str) and (
            "stoa_sk_" in value or "/welcome/" in value
        ):
            continue
        cleaned[key] = value
    return cleaned


class SecretRedactionFilter(logging.Filter):
    """Logging filter that strips credentials from messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                scrub_text(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: scrub_text(val) if isinstance(val, str) else val
                for key, val in record.args.items()
            }
        return True


def install_log_redaction() -> None:
    """Attach the redaction filter to process loggers, including access logs."""
    redactor = SecretRedactionFilter()
    names = ("uvicorn", "uvicorn.access", "uvicorn.error", "control_plane")
    loggers = [logging.getLogger(), *(logging.getLogger(name) for name in names)]
    for target in loggers:
        if not any(isinstance(existing, SecretRedactionFilter) for existing in target.filters):
            target.addFilter(redactor)
