"""Logging filter that redacts provider tokens (CP-1 C.2 defense-in-depth).

Defense-in-depth against accidental token leakage into logs. The primary
fix for C.2 keeps tokens out of subprocess argv (see
``services.git_credentials``); this filter catches the residual risk
where a token reaches a log handler via a path we did not anticipate
(exception ``__repr__``, third-party library logs, etc.).

Patterns are anchored on the documented provider PAT prefixes to avoid
redacting arbitrary strings that merely look tokenish:

- ``ghp_``  : GitHub classic personal access token (36 alnum)
- ``gho_``  : GitHub OAuth access token (36 alnum)
- ``ghu_``  : GitHub user-to-server token
- ``ghs_``  : GitHub server-to-server token
- ``ghr_``  : GitHub refresh token
- ``github_pat_`` : GitHub fine-grained PAT (82 chars incl. underscores)
- ``glpat-`` : GitLab personal access token (20+ alnum/underscore/dash)
"""

from __future__ import annotations

import logging
import re

_REDACTED = "***REDACTED***"

# Each pattern is the provider's documented prefix followed by its
# character class. Ordering matters only insofar as the generic GitHub
# two-letter prefixes would also match ``github_pat_`` — we anchor the
# prefixes explicitly so they don't collide.
_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]{60,}"),
    re.compile(r"gh[opusr]_[A-Za-z0-9]{30,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
]


def redact_secrets(text: str) -> str:
    """Return ``text`` with every known PAT pattern replaced."""
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class SecretRedactor(logging.Filter):
    """Global logging filter that redacts provider PATs in log records.

    Install once at application startup:

        >>> logging.getLogger().addFilter(SecretRedactor())

    Applies to both ``record.msg`` (before formatting) and the formatted
    ``record.args`` values when msg is a format string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        # Also scrub args — commonly used as printf-style format values.
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(v) if isinstance(v, str) else v for v in record.args
                )
        return True
