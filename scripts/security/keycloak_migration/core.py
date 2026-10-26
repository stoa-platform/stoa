"""Strict migration primitives and bounded constants."""

import re
from urllib.parse import quote, unquote, urlsplit


class MigrationError(Exception):
    """Only constant, sanitized messages may cross this boundary."""


BOUNDS = {
    "registrationAllowed": False,
    "accessTokenLifespan": 300,
    "ssoSessionIdleTimeout": 1800,
    "ssoSessionMaxLifespan": 28800,
    "ssoSessionIdleTimeoutRememberMe": 1800,
    "ssoSessionMaxLifespanRememberMe": 28800,
    "clientSessionIdleTimeout": 1800,
    "clientSessionMaxLifespan": 28800,
    "offlineSessionIdleTimeout": 86400,
    "offlineSessionMaxLifespanEnabled": True,
    "offlineSessionMaxLifespan": 604800,
    "revokeRefreshToken": True,
    "refreshTokenMaxReuse": 0,
    "accessCodeLifespan": 60,
    "accessCodeLifespanUserAction": 300,
    "actionTokenGeneratedByUserLifespan": 300,
    "actionTokenGeneratedByAdminLifespan": 3600,
}
CLIENT_BOUNDS = {
    "access.token.lifespan": "300",
    "client.session.idle.timeout": "1800",
    "client.session.max.lifespan": "28800",
    "client.offline.session.idle.timeout": "86400",
    "client.offline.session.max.lifespan": "604800",
}
MAPPER_KEYS = ("name", "protocol", "protocolMapper", "consentRequired", "config")
MAX_BYTES = 16 * 1024 * 1024


def require(condition, message="Invalid policy or API representation; details withheld"):
    if not condition:
        raise MigrationError(message)


def identifier(value):
    require(
        isinstance(value, str)
        and value not in (".", "..")
        and bool(re.fullmatch(r"[A-Za-z0-9_.:@ -]{1,200}", value))
    )
    return quote(value, safe="")


def exact_uri(value, origin=False):
    require(isinstance(value, str))
    decoded = value
    for _ in range(10):
        previous, decoded = decoded, unquote(decoded)
        if decoded == previous:
            break
    require(not any(ord(c) <= 32 or ord(c) == 127 for c in decoded))
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and "?" not in value
        and "#" not in value
        and not any(x in decoded for x in ("*", "+", "\\", "\n", "\r", "\t", " "))
    )
    require(not origin or parsed.path == "")
    # Force validation of the port without exposing a possibly sensitive URL.
    try:
        _ = parsed.port
    except ValueError:
        raise MigrationError("Invalid URL; details withheld") from None


def keys(obj, expected):
    require(isinstance(obj, dict) and set(obj) == set(expected))


def strings(values):
    require(isinstance(values, list) and all(isinstance(x, str) for x in values))
    require(len(values) == len(set(values)))
    for value in values:
        identifier(value)
