"""CAB-2199 / INFRA-1a S2 + Phase 3-A — regression guards for the BASE_DOMAIN derivation validator.

Replaces the prior load-time ``_BASE_DOMAIN = os.getenv(...)`` freeze with a
``model_validator(mode="before")`` that fills in BASE_DOMAIN-derived URL
defaults at instantiation time. The validator uses ``setdefault`` so it
distinguishes ABSENT (derive) from EXPLICITLY-PROVIDED (preserve, including
empty string for derived URLs).

Phase 3-A adds a ``_base_domain_must_not_be_empty`` field validator that
rejects an explicit empty BASE_DOMAIN — closes the BH-INFRA1a-005
inconsistent-state bug where ``Settings(BASE_DOMAIN="")`` preserved the
empty string on the field but the derivation lookup fell back to
``"gostoa.dev"``.

Tests cover:
- Default (no override) — every derived URL renders from ``gostoa.dev``.
- ``BASE_DOMAIN`` override — every derived URL recomputes from the new value
  (this was the bug the load-time freeze hid).
- Explicit URL override — wins over derivation, but other URLs still derive
  from BASE_DOMAIN (per-field independence).
- ``CORS_ORIGINS`` recompute via ``BASE_DOMAIN`` env override + local entries
  preserved.
- ``model_dump()`` exposes resolved URLs (not the empty sentinel).
- Empty-string explicit override preserved for **derived URLs** (caller
  intent honored on KEYCLOAK_URL etc.; documented in CLAUDE.md note #1).
- Empty/whitespace BASE_DOMAIN itself **rejected** at validation
  (Phase 3-A — closes BH-INFRA1a-005).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Run each test in a tmp cwd with no .env file present.

    The repo root holds a developer ``.env`` for local Tilt/k3d work that
    sets ``BASE_DOMAIN=stoa.local`` and ``KEYCLOAK_URL=http://localhost:8080``.
    Without this fixture, those overrides leak into Settings() calls and the
    presence-based assertions become unreliable.
    """
    monkeypatch.chdir(tmp_path)
    # Belt-and-braces: also clear any inherited BASE_DOMAIN/derived-URL env
    # vars in the test process so a CI runner with platform env doesn't
    # poison the test.
    for key in (
        "BASE_DOMAIN",
        "KEYCLOAK_URL",
        "GATEWAY_URL",
        "GATEWAY_ADMIN_PROXY_URL",
        "ARGOCD_URL",
        "ARGOCD_EXTERNAL_URL",
        "GRAFANA_URL",
        "PROMETHEUS_URL",
        "LOGS_URL",
        "VAULT_ADDR",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_base_domain_default_unchanged_for_prod():
    """Default (no override) — all derived URLs render from `gostoa.dev`."""
    s = Settings()
    assert s.BASE_DOMAIN == "gostoa.dev"
    assert s.KEYCLOAK_URL == "https://auth.gostoa.dev"
    assert s.GATEWAY_URL == "https://vps-wm.gostoa.dev"
    assert s.GATEWAY_ADMIN_PROXY_URL == "https://apis.gostoa.dev/gateway/Gateway-Admin-API/1.0"
    assert s.ARGOCD_URL == "https://argocd.gostoa.dev"
    assert s.ARGOCD_EXTERNAL_URL == "https://argocd.gostoa.dev"
    assert s.GRAFANA_URL == "https://grafana.gostoa.dev"
    assert s.PROMETHEUS_URL == "https://prometheus.gostoa.dev"
    assert s.LOGS_URL == "https://grafana.gostoa.dev/explore"
    assert s.VAULT_ADDR == "https://hcvault.gostoa.dev"


def test_base_domain_override_recomputes_derived_urls():
    """Regression for CAB-2199 — formerly frozen at module import.

    Setting ``Settings(BASE_DOMAIN="other.tld")`` previously kept the
    f-string defaults bound to ``gostoa.dev`` because ``_BASE_DOMAIN`` was
    captured at module load time. The new ``mode="before"`` validator
    recomputes every derived URL from the current ``BASE_DOMAIN`` value.
    """
    s = Settings(BASE_DOMAIN="other.tld")
    assert s.BASE_DOMAIN == "other.tld"
    assert s.KEYCLOAK_URL == "https://auth.other.tld"
    assert s.GATEWAY_URL == "https://vps-wm.other.tld"
    assert s.GATEWAY_ADMIN_PROXY_URL == "https://apis.other.tld/gateway/Gateway-Admin-API/1.0"
    assert s.ARGOCD_URL == "https://argocd.other.tld"
    assert s.ARGOCD_EXTERNAL_URL == "https://argocd.other.tld"
    assert s.GRAFANA_URL == "https://grafana.other.tld"
    assert s.PROMETHEUS_URL == "https://prometheus.other.tld"
    assert s.LOGS_URL == "https://grafana.other.tld/explore"
    assert s.VAULT_ADDR == "https://hcvault.other.tld"


def test_explicit_keycloak_url_wins_over_base_domain_derivation():
    """Per-field explicit override is preserved; other fields still derive."""
    s = Settings(BASE_DOMAIN="other.tld", KEYCLOAK_URL="https://kc.bar.io")
    # Explicit override wins
    assert s.KEYCLOAK_URL == "https://kc.bar.io"
    # Other fields still derive from BASE_DOMAIN — not affected by the explicit KEYCLOAK_URL
    assert s.GATEWAY_URL == "https://vps-wm.other.tld"
    assert s.ARGOCD_URL == "https://argocd.other.tld"
    assert s.VAULT_ADDR == "https://hcvault.other.tld"


def test_cors_origins_recomputes_with_base_domain(monkeypatch):
    """CORS_ORIGINS string contains all 6 stage prefixes derived from BASE_DOMAIN
    plus the local-dev entries that are NOT BASE_DOMAIN-derived."""
    monkeypatch.setenv("BASE_DOMAIN", "stage.gostoa.dev")
    s = Settings()
    # All 6 BASE_DOMAIN-derived UI origins present
    assert "https://console.stage.gostoa.dev" in s.CORS_ORIGINS
    assert "https://portal.stage.gostoa.dev" in s.CORS_ORIGINS
    assert "https://staging-console.stage.gostoa.dev" in s.CORS_ORIGINS
    assert "https://dev-portal.stage.gostoa.dev" in s.CORS_ORIGINS
    # Local-dev entries (NOT BASE_DOMAIN-derived) still present
    assert "http://localhost:3000" in s.CORS_ORIGINS
    assert "http://console.stoa.local" in s.CORS_ORIGINS
    # The original gostoa.dev (non-stage) prefix should NOT appear
    # because we overrode the BASE_DOMAIN.
    assert "https://console.gostoa.dev," not in s.CORS_ORIGINS


def test_model_dump_contains_resolved_base_domain_urls():
    """Regression — model_dump() exposes resolved URLs, not the empty sentinel."""
    s = Settings(BASE_DOMAIN="example.io")
    dumped = s.model_dump()
    assert dumped["KEYCLOAK_URL"] == "https://auth.example.io"
    assert dumped["GRAFANA_URL"] == "https://grafana.example.io"
    assert dumped["VAULT_ADDR"] == "https://hcvault.example.io"
    # CORS resolved string also dumps the derived value
    assert "https://console.example.io" in dumped["CORS_ORIGINS"]


def test_empty_explicit_url_is_preserved():
    """``mode="before"`` setdefault preserves caller intent for empty-string overrides.

    Behavior expansion vs the previous frozen-default code (which always
    returned the f-string default regardless of whether the caller passed
    an empty string explicitly). Documented in CLAUDE.md note #1.
    """
    s = Settings(BASE_DOMAIN="example.io", KEYCLOAK_URL="")
    assert s.KEYCLOAK_URL == ""  # explicit empty preserved
    # Other derived fields still apply the BASE_DOMAIN derivation
    assert s.GATEWAY_URL == "https://vps-wm.example.io"
    assert s.VAULT_ADDR == "https://hcvault.example.io"


def test_env_var_override_short_circuits_derivation(monkeypatch):
    """Env-var override (Pydantic-Settings sources env BEFORE the validator
    fires) is preserved by the ``setdefault`` presence check."""
    monkeypatch.setenv("BASE_DOMAIN", "stage.gostoa.dev")
    monkeypatch.setenv("KEYCLOAK_URL", "https://auth.from-env.io")
    s = Settings()
    # Env-set KEYCLOAK_URL wins
    assert s.KEYCLOAK_URL == "https://auth.from-env.io"
    # GATEWAY_URL still derives from BASE_DOMAIN (env did not set it)
    assert s.GATEWAY_URL == "https://vps-wm.stage.gostoa.dev"


@pytest.mark.parametrize("value", ["", "   ", "\n", "\t", " \n\t "])
def test_base_domain_empty_rejected(value):
    """Phase 3-A — explicit empty / whitespace-only BASE_DOMAIN is rejected.

    Closes BH-INFRA1a-005: pre-Phase 3-A, ``Settings(BASE_DOMAIN="")``
    preserved the empty string on the field but the derivation lookup
    (``data.get("BASE_DOMAIN") or "gostoa.dev"``) fell back to
    ``gostoa.dev`` — producing an inconsistent state where derived URLs
    used ``gostoa.dev`` while ``settings.BASE_DOMAIN == ""``. The new
    field validator rejects empty/whitespace at boot.
    """
    with pytest.raises(ValidationError, match="BASE_DOMAIN must not be empty"):
        Settings(BASE_DOMAIN=value)
