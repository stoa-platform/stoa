"""Offline audit primitives and bounded policy constants."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".codex",
    ".claude",
    ".agents",
    ".aws",
    ".ssh",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "__pycache__",
    "target",
    "dist",
}
SUFFIXES = {".json", ".yaml", ".yml", ".sh", ".py", ".md", ".ftl", ".properties"}
DEV_PREFIXES = (
    "deploy/docker-compose/",
    "deploy/demo-federation/",
    "scripts/demo/",
    "scripts/demo-federation/",
    "quickstart/",
    "tests/",
    "e2e/",
    "stoa-gateway/tests/",
    "control-plane-api/tests/",
    "deploy/local/",
)
DEV_FILES = {
    "scripts/setup-e2e-rpo-users.sh",
    "deploy/standalone/jwt-proof.sh",
    ".github/scripts/setup-vault-e2e.sh",
}
BOUNDS = {
    "accessTokenLifespan": 300,
    "accessTokenLifespanForImplicitFlow": 300,
    "ssoSessionIdleTimeout": 1800,
    "ssoSessionMaxLifespan": 28800,
    "clientSessionIdleTimeout": 1800,
    "clientSessionMaxLifespan": 28800,
    "offlineSessionIdleTimeout": 86400,
    "offlineSessionMaxLifespan": 604800,
    "accessCodeLifespan": 60,
    "accessCodeLifespanUserAction": 300,
    "accessCodeLifespanLogin": 300,
    "actionTokenGeneratedByUserLifespan": 300,
    "actionTokenGeneratedByAdminLifespan": 3600,
}
REQUIRED_TIMES = (
    "accessTokenLifespan",
    "ssoSessionIdleTimeout",
    "ssoSessionMaxLifespan",
    "offlineSessionIdleTimeout",
    "offlineSessionMaxLifespan",
)
ATTR_BOUNDS = {
    "access.token.lifespan": 300,
    "client.session.idle.timeout": 1800,
    "client.session.max.lifespan": 28800,
    "client.offline.session.idle.timeout": 86400,
    "client.offline.session.max.lifespan": 604800,
}
API_CLIENTS = {
    "control-plane-ui",
    "stoa-portal",
    "stoa-mcp-gateway",
    "stoa-gateway",
    "stoa-identity-governance",
    "control-plane-api",
}


@dataclass(frozen=True, order=True)
class Finding:
    file: str
    line: int
    rule: str
    severity: str
    environment: str
    message: str


def environment(path: str, mode: str = "auto") -> str:
    if mode != "auto":
        return mode
    return "dev" if path.startswith(DEV_PREFIXES) or path in DEV_FILES else "prod"


def credential_path(p: Path) -> bool:
    n = p.name.lower()
    return (
        n.startswith(".env")
        or "credentials" in n
        or n in {".gitconfig", ".netrc"}
        or p.suffix in {".pem", ".key", ".p12", ".tfvars"}
    )


def files(root: Path):
    """Do not follow symlinks, including symlinked parents."""
    for p in sorted(root.iterdir()):
        if p.is_symlink() or p.name in SKIP_DIRS:
            continue
        if p.is_dir():
            yield from files(p)
        elif p.suffix in SUFFIXES or p.name == "Dockerfile" or p.suffix == ".env":
            yield p


def relevant(path: str, text: str) -> bool:
    if path.endswith(".json") and (
        "realm" in Path(path).name.lower() or re.search(r'"realm"\s*:', text)
    ):
        return True
    return bool(
        re.search(
            r"(?i)keycloak|registrationAllowed|directAccessGrantsEnabled|"
            r"implicitFlowEnabled|oidc-audience-mapper|/admin/realms|"
            r"pkce.code.challenge|kind:\s*NetworkPolicy",
            text,
        )
    )


def category(path: str, text: str) -> str:
    if Path(path).name in {
        "keycloak_audit.py",
        "test_keycloak_audit.py",
        "test_bootstrap_draft.py",
    }:
        return "checker"
    if path.endswith(".md"):
        return "documentation"
    if path.startswith("apis/") or path.endswith("openapi-snapshot.json") or "/locales/" in path:
        return "consumer"
    if "kind: NetworkPolicy" in text:
        return "network"
    if (
        re.search(r'"realm"\s*:|"clientId"\s*:', text)
        or re.search(r"kcadm.sh.*(?:create|update)|/admin/realms|KCADM.*(?:create|update)", text)
        or "oauth2:" in text
        or path.endswith("stoa-realm-totp.json")
    ):
        return "bootstrap" if not path.startswith("control-plane-api/src/") else "runtime"
    if path.endswith((".yaml", ".yml", ".sh")) or Path(path).name == "Dockerfile":
        return "wiring"
    return "consumer"


def json_objects(text: str):
    """Decode JSON payloads, including escaped shell double-quoted payloads.

    Never evaluates substitutions. Failed payloads are reported separately by
    audit_text; finding a nested object does not certify its enclosing script.
    """
    decoder = json.JSONDecoder()
    seen = set()
    for candidate in (text, text.replace('\\"', '"')):
        end = 0
        for m in re.finditer(r"\{", candidate):
            if m.start() < end:
                continue
            try:
                obj, size = decoder.raw_decode(candidate[m.start() :])
            except ValueError:
                continue
            if isinstance(obj, dict):
                line = candidate.count("\n", 0, m.start()) + 1
                key = (line, json.dumps(obj, sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    yield obj, line
                end = m.start() + size


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def line_for(text: str, key: str, start: int = 1) -> int:
    # Anchor to the start of the representation; no global first-key lookup.
    lines = text.replace('\\"', '"').splitlines()
    pattern = re.compile(r"(?<![\w.])" + re.escape(key) + r'(?:["\x27]?\s*[:=]|["\x27]\s*:)')
    for i in range(max(0, start - 1), len(lines)):
        if pattern.search(lines[i]):
            return i + 1
    return start


def is_true(v):
    return v is True or v == "true"


def bounded(v, maximum):
    # bool is an int subclass: explicitly reject it. Zero means unlimited or
    # inheritance in several KC settings and never passes as a positive bound.
    return (
        not isinstance(v, bool)
        and re.fullmatch(r"[0-9]+", str(v)) is not None
        and 0 < int(v) <= maximum
    )
