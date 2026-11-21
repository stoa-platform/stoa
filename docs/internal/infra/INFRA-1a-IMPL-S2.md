# INFRA-1a — S2 implementation: `_BASE_DOMAIN` derivation validator

> **Companion to**: `docs/infra/INFRA-1a-PLAN.md` §2.2.
> **Scope**: implementation code + test corpus for sub-scope S2 only.
> **Created**: 2026-04-29 (revision v3 — Council Stage 2 adjustment #3, plan-length trim).

This file holds the implementation code blocks extracted from the master plan to keep the Christophe-readable surface ≤ 30 KB. The master plan retains the §2.2.a (files to touch), §2.2.b (behavioral preservation), and §2.2.e (risks) — only the §2.2.c (code) and §2.2.d (tests) live here.

---

## Specific changes (master plan §2.2.c)

**Before** (`config.py:17, 117, 129, ...`):

```python
_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")
...
class Settings(BaseSettings):
    BASE_DOMAIN: str = _BASE_DOMAIN
    KEYCLOAK_URL: str = f"https://auth.{_BASE_DOMAIN}"
    GATEWAY_URL: str = f"https://vps-wm.{_BASE_DOMAIN}"
    GATEWAY_ADMIN_PROXY_URL: str = f"https://apis.{_BASE_DOMAIN}/gateway/Gateway-Admin-API/1.0"
    ARGOCD_URL: str = f"https://argocd.{_BASE_DOMAIN}"
    ARGOCD_EXTERNAL_URL: str = f"https://argocd.{_BASE_DOMAIN}"
    GRAFANA_URL: str = f"https://grafana.{_BASE_DOMAIN}"
    PROMETHEUS_URL: str = f"https://prometheus.{_BASE_DOMAIN}"
    LOGS_URL: str = f"https://grafana.{_BASE_DOMAIN}/explore"
    CORS_ORIGINS: str = (
        f"https://console.{_BASE_DOMAIN}, ..."  # 6 references
    )
```

**Pattern A — `@property` recompute** (Section 3 #2 alternative):

```python
# Module-level _BASE_DOMAIN REMOVED. BASE_DOMAIN now reads via Pydantic.

class Settings(BaseSettings):
    BASE_DOMAIN: str = "gostoa.dev"  # default; env BASE_DOMAIN overrides via Pydantic

    # Stored fields become None|str sentinels: when set explicitly via env
    # or constructor, they win; when None, the @property derives from BASE_DOMAIN.
    KEYCLOAK_URL: str | None = None
    GATEWAY_URL: str | None = None
    GATEWAY_ADMIN_PROXY_URL: str | None = None
    ARGOCD_URL: str | None = None
    ARGOCD_EXTERNAL_URL: str | None = None
    GRAFANA_URL: str | None = None
    PROMETHEUS_URL: str | None = None
    LOGS_URL: str | None = None
    CORS_ORIGINS: str | None = None

    @property
    def keycloak_public_url(self) -> str:
        return self.KEYCLOAK_URL or f"https://auth.{self.BASE_DOMAIN}"

    # ... 8 more properties
```

**Trade-off**: this changes the type signature of 9 fields from `str` to `str | None`. Consumers reading `settings.KEYCLOAK_URL` now see `Optional[str]`. **Mypy will catch every consumer.**

**Pattern B — `model_validator(mode="before")` (RECOMMENDED)** — single validator that fills in **absent** URLs (not just falsy ones) from `BASE_DOMAIN`. Distinguishing absent vs explicitly-fournis avoids silently overriding `KEYCLOAK_URL=""` (empty-string explicit override would otherwise be re-derived in an `after` validator).

```python
class Settings(BaseSettings):
    BASE_DOMAIN: str = "gostoa.dev"

    KEYCLOAK_URL: str = ""  # default; absent in input dict → resolved by validator
    GATEWAY_URL: str = ""
    GATEWAY_ADMIN_PROXY_URL: str = ""
    ARGOCD_URL: str = ""
    ARGOCD_EXTERNAL_URL: str = ""
    GRAFANA_URL: str = ""
    PROMETHEUS_URL: str = ""
    LOGS_URL: str = ""
    CORS_ORIGINS: str = ""

    @model_validator(mode="before")
    @classmethod
    def _derive_urls_from_base_domain(cls, data: object) -> object:
        """Inject BASE_DOMAIN-derived defaults for URL fields ABSENT from input.

        Distinguishes absent (use derivation) from empty-string (caller intent
        — preserve as-is). Pydantic's BaseSettings flattens env vars + dotenv
        + secrets into the input dict before this hook fires, so explicit
        ``KEYCLOAK_URL=https://x.io`` from any source short-circuits the
        derivation. ``KEYCLOAK_URL=""`` (explicit empty) is also preserved.
        """
        if not isinstance(data, dict):
            return data

        base_domain = data.get("BASE_DOMAIN") or "gostoa.dev"

        derived = {
            "KEYCLOAK_URL": f"https://auth.{base_domain}",
            "GATEWAY_URL": f"https://vps-wm.{base_domain}",
            "GATEWAY_ADMIN_PROXY_URL": (
                f"https://apis.{base_domain}/gateway/Gateway-Admin-API/1.0"
            ),
            "ARGOCD_URL": f"https://argocd.{base_domain}",
            "ARGOCD_EXTERNAL_URL": f"https://argocd.{base_domain}",
            "GRAFANA_URL": f"https://grafana.{base_domain}",
            "PROMETHEUS_URL": f"https://prometheus.{base_domain}",
            "LOGS_URL": f"https://grafana.{base_domain}/explore",
            "CORS_ORIGINS": (
                f"https://console.{base_domain},https://portal.{base_domain},"
                f"https://staging-console.{base_domain},https://staging-portal.{base_domain},"
                f"https://dev-console.{base_domain},https://dev-portal.{base_domain},"
                "http://localhost:3000,http://localhost:3002,http://localhost:5173,"
                "http://console.stoa.local,http://portal.stoa.local,http://api.stoa.local"
            ),
        }

        for field, value in derived.items():
            data.setdefault(field, value)  # absent → injected; present (even "") → kept

        return data
```

**Why `mode="before"` + `setdefault` wins over `mode="after"` + `if not ...`**:

- `setdefault` keys on **presence**, not truthiness — so `KEYCLOAK_URL=""` is preserved, not silently re-derived. Important for tests that probe empty-string semantics, and for the (rare) operator who deliberately blanks a URL.
- Field types stay `str` (no Optional churn for 9 fields × 24 importers).
- `Settings(BASE_DOMAIN="other.tld").KEYCLOAK_URL` recomputes correctly because `BASE_DOMAIN` is read from the input dict before field validation.
- Explicit env overrides (`KEYCLOAK_URL=https://kc.foo.com`) win — Pydantic-Settings flattens env/dotenv into the input dict before the `before` hook.
- `model_dump()` returns resolved strings, no consumer change.

**Behavior change to verify in tests**: the explicit-empty-string preservation is a **new** semantic vs the original frozen-default code (which never preserved empty — every load returned the f-string default). Document explicitly in CLAUDE.md note #1; cover with `test_empty_explicit_url_is_preserved`.

**Decision pinned to master plan Section 3 #2**: `@property` vs `model_validator(mode="before")`. Default plan picks **validator (mode="before")**.

---

## Tests to add (master plan §2.2.d)

`control-plane-api/tests/test_config_base_domain_property.py`:

```python
def test_base_domain_default_unchanged_for_prod():
    s = Settings()
    assert s.KEYCLOAK_URL == "https://auth.gostoa.dev"
    assert s.GATEWAY_URL == "https://vps-wm.gostoa.dev"
    assert s.ARGOCD_URL == "https://argocd.gostoa.dev"
    # ... 6 more

def test_base_domain_override_recomputes_derived_urls():
    """Regression for CAB-2199 — formerly frozen at module import."""
    s = Settings(BASE_DOMAIN="other.tld")
    assert s.KEYCLOAK_URL == "https://auth.other.tld"
    assert s.GATEWAY_URL == "https://vps-wm.other.tld"
    assert s.ARGOCD_URL == "https://argocd.other.tld"

def test_explicit_keycloak_url_wins_over_base_domain_derivation():
    s = Settings(BASE_DOMAIN="other.tld", KEYCLOAK_URL="https://kc.bar.io")
    assert s.KEYCLOAK_URL == "https://kc.bar.io"
    assert s.GATEWAY_URL == "https://vps-wm.other.tld"  # still derived

def test_cors_origins_recomputes_with_base_domain(monkeypatch):
    monkeypatch.setenv("BASE_DOMAIN", "stage.gostoa.dev")
    s = Settings()
    assert "https://console.stage.gostoa.dev" in s.CORS_ORIGINS
    assert "http://localhost:3000" in s.CORS_ORIGINS  # local entries preserved

def test_model_dump_contains_resolved_base_domain_urls():
    """Regression — model_dump() exposes resolved URLs, not the empty sentinel."""
    s = Settings(BASE_DOMAIN="example.io")
    dumped = s.model_dump()
    assert dumped["KEYCLOAK_URL"] == "https://auth.example.io"
    assert dumped["GRAFANA_URL"] == "https://grafana.example.io"

def test_empty_explicit_url_is_preserved():
    """mode='before' setdefault preserves caller intent for empty-string overrides.

    This is a behavior expansion vs the previous frozen-default code (which
    always returned the f-string default). Documented in CLAUDE.md note #1.
    """
    s = Settings(BASE_DOMAIN="example.io", KEYCLOAK_URL="")
    assert s.KEYCLOAK_URL == ""  # explicit empty preserved
    assert s.GATEWAY_URL == "https://vps-wm.example.io"  # derivation still applies
```

7 tests minimum (one per derived URL "family": KEYCLOAK, GATEWAY+PROXY, ARGOCD, GRAFANA+PROMETHEUS+LOGS, CORS) **+ model_dump regression + empty-string preservation**.
