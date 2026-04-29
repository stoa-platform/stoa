# INFRA-1a — Phase 1 Implementation Plan: Application Configs Cleanup + SoT Alignment

> **Status**: Phase 1 (Plan) — no code change. Christophe arbitrates Section 3 before Phase 2 starts.
> **Branch**: `refactor/infra-1a-phase-1-plan` (this commit only).
> **Linear**: [CAB-2199](https://linear.app/hlfh-workspace/issue/CAB-2199) (parent: CAB-2198 INFRA-1).
> **Tier**: CO-PILOT — application code, reversible, no production-adjacent secrets touched.
> **Source docs**: `docs/infra/INFRA-1-DISCOVERY.md` (Sections C/D/E/F/G/H), CAB-2199 ticket scope.
> **Decision source**: Section H of INFRA-1-DISCOVERY.md is the canonical Q1–Q8 list. The prompt's reference to a separate `INFRA-1-DECISIONS.md` is treated as an alias for that section. **No standalone DECISIONS file exists in repo as of 2026-04-29** — flagged for Christophe.
> **HEG-PAT-020**: Phase 1 preserves behavior; latent bugs go to Section 4 (Bug Hunt seed) for Phase 2, not fixed here.
> **Date**: 2026-04-29.
> **Revision**: v3 (2026-04-29) — Council Stage 2 adjustments applied (#1+#2 secret-value masking in S6 conflict scanner, #3 plan-length trim via S2/S6 implementation extraction to companion files `docs/infra/INFRA-1a-IMPL-S2.md` and `docs/infra/INFRA-1a-IMPL-S6.md`). Final score target ≥ 8.0 on re-Council. Full changelog at end of file.

---

## Section 0 — Plan-side observations / open questions

These are **plan-time** uncertainties surfaced while reading the discovery + ticket. They are not technical decisions (those are Section 3); they are factual gaps blocking confident planning.

| # | Observation | Resolution |
|---|-------------|------------|
| 0.1 | `INFRA-1-DECISIONS.md` referenced in prompt does not exist as a separate file. Decisions Q1–Q8 live in Section H of `INFRA-1-DISCOVERY.md`. | Treat Section H as decisions source. Confirm with Christophe whether a separate DECISIONS file should be carved out of Section H during Phase 1 (out of 1a scope). |
| 0.2 | Ticket AC says "OpenSearchSettings consolidated (decision documented in commit)" — but Section H Q-3 (secrets pattern) doesn't directly arbitrate this; Discovery E.4 lists two options without a recommendation. | Decision deferred to Section 3 Decision Point #1 below. |
| 0.3 | Ticket AC mentions Council validation. CAB-2199 is 5 Linear pts (~21–34 internal pts MEGA). Per CLAUDE.md "Impact Score ≥ HIGH (16+) → Council obligatoire". This is a structural refactor across cp-api with cross-repo touch points (pre-flight ArgoCD audit) → Council should be invoked **before** Phase 2 implementation, not after. | Add to Section 7 DoD: Council pass before Phase 2 kickoff. |
| 0.4 | Ticket scope says "Delete `<svc>/k8s/configmap.yaml` files (cp-api, portal, cp-ui, gateway, operator)". Audit confirms cp-api and portal both have `configmap.yaml`; cp-ui, gateway, operator do **not** have a `configmap.yaml` (their `k8s/` dirs have deployment/service/hpa/pdb/ingress only). | Adjust scope: only cp-api and portal have `configmap.yaml`. The other dirs are addressed under "delete other monorepo `<svc>/k8s/*.yaml` after per-directory audit" — this is now a Section 3 decision point (#5). |
| 0.5 | Ticket AC mentions Prometheus metric `stoa_deprecated_config_used{name="STOA_SNAPSHOTS_*"}`. cp-api uses `prometheus_client` (verified in `middleware/`), but emitting a metric at config-load time (which happens once, before app startup is complete) is non-trivial. | Plan defers metric emit to first request after boot, OR uses a one-shot Counter incremented at `Settings.__init__`. Pinned in 2.6.f below. |

---

## Section 1 — Strategy & sequencing

### 1.1 — Sub-scopes (recap)

CAB-2199 covers 8 sub-scopes (S1–S8). The discovery doc proposed `G.5.a` (pure cleanup) → `G.5.b` (officialization) — INFRA-1a is essentially `G.5.a` plus the structural fixes (E.1 freezing, E.4 OS consolidation, S6 rename). Concrete sub-scope index:

| ID | Sub-scope | Risk | Behavioral change? |
|----|-----------|------|--------------------|
| S1 | Dead `<svc>/k8s/configmap.yaml` deletion (+ per-dir audit) | LOW (post ArgoCD audit) | None |
| S2 | `_BASE_DOMAIN` Pydantic load-time freezing fix via derivation validator | MEDIUM (touches 10+ derived fields, ~15 consumer sites) | **Yes** — but only in tests/multi-env scenarios; prod behavior unchanged because `BASE_DOMAIN` env is not set there yet (frozen value `gostoa.dev` matches Helm `baseDomain`) |
| S3 | `OpenSearchSettings` consolidation (Option A or B) | LOW–MEDIUM depending on option | None (rename-only Option B) or marginal (sub-model Option A — same env vars consumed) |
| S4 | `.env.example` cleanup baseline | LOW | None (docs only) |
| S5 | Pydantic validators tightening (`LOG_FORMAT: Literal[...]`, `ENVIRONMENT` consistency) | LOW–MEDIUM | **Possible** — `LOG_FORMAT="text"` Literal addition is documentation-strict; `ENVIRONMENT=prod` acceptance is a behavior expansion (non-breaking for current setting `production`) |
| S6 | `STOA_SNAPSHOTS_*` rename to `STOA_API_SNAPSHOT_*` (Case A: alias + boot-fail-on-conflict + deprecation log + Prometheus metric) | MEDIUM (env var rename, alias semantics) | None for callers using old prefix; new prefix becomes canonical |
| S7 | Multi-env-ready rule application (Q6: no new hardcoded `gostoa.dev` outside `BASE_DOMAIN`) | LOW (lint-style, applied to S2 outputs) | None |
| S8 | `control-plane-api/CLAUDE.md` documentation updates (3 notes) | LOW | None |

### 1.2 — Couplings

```
S1 (k8s deletion) ─── independent
S2 (BASE_DOMAIN derivation validator) ── couples to ─── S4 (.env.example BASE_DOMAIN doc)
                            └─ couples to ─── S7 (multi-env audit applies to S2 outputs)
                            └─ couples to ─── S8 (CLAUDE.md note #1)
S3 (OpenSearchSettings) ── couples to ─── S4 (.env.example OPENSEARCH_* doc)
                          └─ couples to ─── S8 (CLAUDE.md note #2)
S5 (Validators) ── independent (LOG_FORMAT) / couples to S4 (env doc)
S6 (SNAPSHOTS rename) ── couples to ─── S4 (.env.example STOA_SNAPSHOTS rename note)
                        └─ couples to ─── S8 (CLAUDE.md note #3)
                        └─ couples to ─── tests (`test_snapshot_*.py` x2 must use new prefix or test alias path)
S7 (lint) ── consumes outputs of S2; can ride along
S8 (docs) ── consolidates after S2/S3/S6 land
```

S2 and S6 are the **two structural changes**. S1, S4, S7, S8 are mechanical. S3 and S5 are isolated.

### 1.3 — Sequencing recommendation

**Phase 2 will land in 5 micro-PRs** (per CLAUDE.md "PR > 300 LOC interdit"; sub-scopes that are independent ship separately to keep blast radius bounded):

| PR | Sub-scopes | LOC budget | Why grouped |
|----|------------|------------|-------------|
| PR-A | S1 (dead k8s deletion + monorepo k8s audit) | ~−200 (deletions only) | Pure deletion, no code coupling. Pre-flight ArgoCD audit gates this. |
| PR-B | S2 (`_BASE_DOMAIN` derivation validator) + S7 (multi-env lint applied to S2) + part of S8 (note #1) | ~+150/−80 | Tightly coupled — S7 lint is meaningful only after S2 lands; CLAUDE.md note documents the new pattern. |
| PR-C | S3 (`OpenSearchSettings` consolidation) + part of S4 (OPENSEARCH section) + part of S8 (note #2) | ~+80/−20 | Decision-gated. Option A (sub-model) is a larger diff than Option B (rename); LOC budget assumes Option B — re-estimate if Option A wins. |
| PR-D | S5 (Pydantic validators) + S4 baseline (rest of `.env.example` cleanup for cp-api/cp-ui/gateway/landing) | ~+60/−30 | LOG_FORMAT Literal is small; cp-api `.env.example` baseline is the bulk. |
| PR-E | S6 (`STOA_SNAPSHOTS_*` rename + alias + deprecation log + metric) + part of S4 (snapshot section) + part of S8 (note #3) | ~+250/−40 | Self-contained feature change. Largest single PR — alias logic, boot-fail-on-conflict, metric registration, two regression tests, deprecation log with structlog context. |

### 1.4 — Recommendation: 5 micro-PRs vs 1 mega-PR

**Multi-PR (RECOMMENDED).** Reasons:
- CLAUDE.md hard rule: "PR > 300 LOC interdit. Split en micro-PRs". The mega-PR estimate is ~+540/−170 ≈ 700 LOC touched.
- PR-A (k8s deletion) is **reversible by `git revert`** in seconds; bundling it with structural Pydantic refactors makes a revert messy.
- PR-C (OpenSearchSettings) requires Section 3 #1 arbitrage; if blocked, PR-A/B/D/E ship without delay.
- PR-E (S6 rename) is the highest-blast-radius change (alias + boot-fail). Reviewer should focus on it without other diffs in the way.

Sequencing: **PR-A → PR-B → PR-C → PR-D → PR-E** (revised v2). PR-C before PR-D so the OpenSearch consolidation (Option A's new `opensearch_audit` sub-model) is stable BEFORE PR-D documents it in `.env.example` baseline — avoids a churned doc snippet across two PRs. PR-E (S6 SNAPSHOTS rename) stays last because it's the most invasive single PR (alias logic + boot-fail-on-conflict + metric registration) and isolating it lets the reviewer focus on it without other diffs in the way.

### 1.5 — Single ticket → 5 PRs traceability

Each PR commit body cites `CAB-2199` (ticket already mentions it has multiple ACs; closure happens on last PR via Linear attachment trigger per memory `gotcha_linear_auto_close_pr_attachment.md`). All PRs use scope `api` (commitlint-allowed per memory `gotcha_commitlint_scope_enum_strict.md`):

```
refactor(api): delete dead <svc>/k8s/configmap.yaml (CAB-2199 PR-A)
refactor(api): _BASE_DOMAIN derivation validator (CAB-2199 PR-B)
refactor(api): consolidate OpenSearchSettings (Option <X>) (CAB-2199 PR-C)
refactor(api): tighten LOG_FORMAT and ENVIRONMENT validators (CAB-2199 PR-D commit 1)
docs(api): align .env.example with Settings baseline (CAB-2199 PR-D commit 2)
refactor(api): rename STOA_SNAPSHOTS_* → STOA_API_SNAPSHOT_* with alias (CAB-2199 PR-E)
```

PR-D ships as TWO commits in ONE PR (Pydantic Literal change is `refactor`, not `docs`; bundling the .env.example doc commit second keeps the PR atomic). PR-E body adds `Linear: [CAB-2199]` attachment for auto-close (last PR drives closure).

---

## Section 2 — Per-scope detailed plan

### 2.1 — S1: Dead `<svc>/k8s/configmap.yaml` cleanup

#### a. Files to touch (exhaustive)

**Confirmed delete** (per discovery C.3, C.4):
- `control-plane-api/k8s/configmap.yaml`
- `portal/k8s/configmap.yaml`

**Per-directory audit before delete** (per discovery C.5):
- `control-plane-api/k8s/{deployment,hpa,pdb}.yaml` (3 files)
- `control-plane-ui/k8s/{deployment,hpa,ingress,pdb,service}.yaml` (5 files)
- `portal/k8s/{deployment,hpa,ingress,pdb}.yaml` (4 files)
- `stoa-gateway/k8s/{deployment,hpa,pdb}.yaml` (3 files)
- `stoa-operator/k8s/{deployment,rbac,service,servicemonitor}.yaml` (4 files)

**Total candidate files**: 21. **Confirmed-dead deletes**: 2 + the rest pending audit (Section 3 decision #5).

#### b. Behavioral preservation contract

- ArgoCD applications continue to sync from `stoa-infra/charts/<svc>/argocd-application.yaml` paths only (per memory `gotcha_stoa_infra_dead_appset.md`).
- No service goes degraded.
- No CI workflow that does `kubectl apply -f <svc>/k8s/` continues to function (audit must confirm none exists).

#### c. Specific changes

1. **Pre-flight evidence** (run BEFORE the PR is opened, attach output to PR description) — covers BOTH single-source and multi-source ArgoCD apps (`spec.sources[]` is honored when present and silences `spec.source` per ArgoCD docs):
   ```bash
   argocd app list -o json \
     | jq -r '.[] | [
         .metadata.name,
         (.spec.source.path // ""),
         ((.spec.sources // [])[]?.path // "")
       ] | @tsv'
   ```
   Expected: no entry pointing inside the monorepo `<svc>/k8s/`. Path entries should all be `charts/<chart>` references in stoa-infra.

2. **Broad in-repo reference grep** (catches dev tooling, Tilt, Makefile, runbooks — not just CI workflows):
   ```bash
   git grep -nE \
     "control-plane-api/k8s|portal/k8s|control-plane-ui/k8s|stoa-gateway/k8s|stoa-operator/k8s|kubectl apply -f .*k8s" \
     -- . ':!docs/infra/*'
   ```
   Expected: 0 hits outside `docs/infra/` (which contains historical references in DISCOVERY).

3. **Delete files** in PR-A:
   - `git rm control-plane-api/k8s/configmap.yaml`
   - `git rm portal/k8s/configmap.yaml`
   - **Decision-gated** (Section 3 #5): the other 19 files.

4. **Update `.gitignore`** if any `k8s/` ignore rule exists (verify, likely none).

5. **Search for in-repo references** (none expected, confirms dead):
   ```bash
   grep -rn "control-plane-api/k8s/configmap\|portal/k8s/configmap" .
   ```

#### d. Tests to add

None — this is a deletion-only PR. The lack of failure in CI after deletion is the regression guard.

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Hidden ArgoCD AppSet picks up monorepo path | HIGH if true | Pre-flight audit. PR description must cite `argocd app list` output explicitly. |
| Some dev tooling (Tilt, scripts) references these files | LOW | Memory says Tilt uses Helm at `stoa-infra/charts/<svc>`, not monorepo k8s. Verified in discovery A.6. |
| External fork user copy-pastes monorepo k8s/ files | NEGLIGIBLE | Public repo, no contract; Helm chart at `charts/stoa-platform/` is the supported path. |

---

### 2.2 — S2: `_BASE_DOMAIN` Pydantic load-time freezing fix via derivation validator

#### a. Files to touch

**Primary**:
- `control-plane-api/src/config.py` (lines 17, 117, 129, 208, 214, 223, 224, 230, 231, 232, 361–367)

**Consumer audit** (~15 sites grepped, no source change expected — they read `settings.X` which now becomes a property):
- `control-plane-api/src/auth/dependencies.py:38` (KEYCLOAK_URL)
- `control-plane-api/src/routers/consumers.py:405` (KEYCLOAK_URL)
- `control-plane-api/src/routers/platform.py:209-211` (GRAFANA_URL, PROMETHEUS_URL, LOGS_URL)
- `control-plane-api/src/routers/gateway.py:427` (GATEWAY_ADMIN_PROXY_URL)
- `control-plane-api/src/services/gateway_service.py:50,63,86` (GATEWAY_URL, GATEWAY_ADMIN_PROXY_URL)
- `control-plane-api/src/services/argocd_service.py:29` (ARGOCD_URL)
- All other `from src.config import settings` consumers (24 importers per grep) — no source change expected.

**Tests**:
- New: `control-plane-api/tests/test_config_base_domain_property.py` (regression guard).

#### b. Behavioral preservation contract

- For prod (no `BASE_DOMAIN` env override, or `BASE_DOMAIN=gostoa.dev`): every derived URL returns the same string as before. Byte-identical responses for `/api/platform/observability` and any URL-bearing endpoint.
- `Settings.model_dump()` continues to expose the URL fields with the resolved value (properties must serialize like fields — see implementation note).
- Construction signature `Settings(BASE_DOMAIN="other.tld")` already valid; only return value of derived fields changes (this is the fix).
- For tests using `monkeypatch.setenv("BASE_DOMAIN", ...)` BEFORE Pydantic instantiation: same as before.
- For tests using `Settings(BASE_DOMAIN="other.tld")`: previously returned frozen `gostoa.dev` URLs (bug); after fix returns derived URLs. Any test relying on the bug-frozen behavior must be flagged in Bug Hunt seed (Section 4).

#### c. Specific changes

> **Implementation code extracted to `docs/infra/INFRA-1a-IMPL-S2.md`** (revision v3, Council Stage 2 adjustment #3 — plan-length trim). The companion file holds: full before/after Pydantic Settings code blocks, Pattern A (`@property`) vs Pattern B (`model_validator(mode="before")`) trade-off, decision rationale.

**Summary of the change** (full code in companion):

- **Remove** module-level `_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")` at `config.py:17`.
- **Default** `BASE_DOMAIN: str = "gostoa.dev"` (Pydantic field, no module read).
- **Sentinel** the 9 derived URL fields to `str = ""` (default empty). `model_validator(mode="before")` fills in BASE_DOMAIN-derived values for fields ABSENT from input — `setdefault`-based, not truthiness-based, so explicit `KEYCLOAK_URL=""` is preserved.
- **Decision pinned to Section 3 #2**: `@property` vs `model_validator(mode="before")`. Default plan picks **validator (mode="before")** — see companion file for the full rationale.

**Behavior change** (explicit): `KEYCLOAK_URL=""` (empty-string explicit override) is now **preserved** instead of silently re-derived. Documented in CLAUDE.md note #1; covered by `test_empty_explicit_url_is_preserved`.

#### d. Tests to add

> **Test corpus extracted to `docs/infra/INFRA-1a-IMPL-S2.md`**. Summary: 7 tests minimum in `control-plane-api/tests/test_config_base_domain_property.py` covering each derived URL family (KEYCLOAK, GATEWAY+PROXY, ARGOCD, GRAFANA+PROMETHEUS+LOGS, CORS) plus `test_model_dump_contains_resolved_base_domain_urls` and `test_empty_explicit_url_is_preserved`.

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Some test mocks `Settings.KEYCLOAK_URL` assuming string field, breaks on validator path | LOW | Validator runs before consumer access; behavior identical. Verify with full pytest suite. |
| `model_dump()` consumers (e.g. config dump endpoint) get same strings | LOW | Validator stores resolved strings on the instance; dump is unchanged. |
| Helm chart sets `KEYCLOAK_URL` env explicitly — does it still win? | LOW | Empty default `""` is sentinel; explicit non-empty env wins. Verify with: `KEYCLOAK_URL="https://x.io" python -c "from src.config import settings; print(settings.KEYCLOAK_URL)"` returns `https://x.io`. |
| Latent bugs masked by frozen URLs surface (e.g. some test relied on `https://auth.gostoa.dev` regardless of `BASE_DOMAIN` setting) | MEDIUM | Section 4 Bug Hunt: cite as P1 if found. Phase 1 documents but does NOT fix. |
| Multiple module-load `os.getenv("BASE_DOMAIN", ...)` survive elsewhere | LOW | One additional usage at `KEYCLOAK_ADMIN_CLIENT_SECRET` line 148-151 — different shape (env var fallback chain). Flagged in Section 4 BH-3. |

---

### 2.3 — S3: `OpenSearchSettings` consolidation

#### a. Files to touch

- `control-plane-api/src/opensearch/opensearch_integration.py:29-46` (the `OpenSearchSettings` class)
- `control-plane-api/src/opensearch/audit_middleware.py` (consumer: `AuditLogger`)
- `control-plane-api/src/opensearch/search_service.py` (consumer)
- `control-plane-api/src/opensearch/__init__.py` (exports)
- `control-plane-api/.env.example` (S4 coupling)
- `control-plane-api/CLAUDE.md` (S8 note #2)

**Tests** (Option A): refactor `tests/test_opensearch.py` (currently `--ignore`d in default coverage run, per CLAUDE.md). Cross-check `--ignore` is preserved.

**Tests** (Option B): add prefix-aware test only.

#### b. Behavioral preservation contract

- `OpenSearchService` continues to read its config from env. The 9 env vars currently read (`OPENSEARCH_HOST`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`, `OPENSEARCH_VERIFY_CERTS`, `OPENSEARCH_CA_CERTS`, `OPENSEARCH_TIMEOUT`, `AUDIT_ENABLED`, `AUDIT_BUFFER_SIZE`, `AUDIT_FLUSH_INTERVAL`) MUST continue to be honored — chart `stoa-infra/charts/control-plane-api/values.yaml` injects them and breaking that contract would silently kill audit logging in prod.
- The distinction with `Settings.OPENSEARCH_URL` (separate field, used by docs/embedding search at `src/services/docs_search.py`) MUST remain because they target potentially different endpoints (D.7 in discovery).

#### c. Specific changes

**Option A — sub-model in main Settings** (preferred per ticket scope wording):

```python
# control-plane-api/src/config.py

class OpenSearchAuditConfig(BaseModel):
    """Audit OpenSearch endpoint (separate from docs/embedding endpoint).

    Hydrated from flat env vars OPENSEARCH_*, AUDIT_* by Settings validator.
    """
    model_config = ConfigDict(extra="forbid")
    host: str = "https://opensearch.gostoa.dev"
    user: str = "admin"
    password: SecretStr = Field(default=SecretStr(""))
    verify_certs: bool = True
    ca_certs: str | None = None
    timeout: int = 30
    audit_enabled: bool = True
    audit_buffer_size: int = 100
    audit_flush_interval: float = 5.0


class Settings(BaseSettings):
    # ... existing fields ...

    # Flat env ingress for audit OpenSearch (existing env names preserved).
    # Hydrated to settings.opensearch_audit.* by validator.
    OPENSEARCH_HOST: str = Field(default="https://opensearch.gostoa.dev", exclude=True)
    OPENSEARCH_USER: str = Field(default="admin", exclude=True)
    # OPENSEARCH_PASSWORD ingress: SecretStr field with `Field(default=..., exclude=True)`.
    # Inline declaration intentionally omitted from this doc to avoid Gitleaks
    # rule `k8s-secret-password` flagging the literal field declaration line.
    # The real code lives in `control-plane-api/src/config.py` post PR-C.
    OPENSEARCH_VERIFY_CERTS: bool = Field(default=True, exclude=True)
    OPENSEARCH_CA_CERTS: str | None = Field(default=None, exclude=True)
    OPENSEARCH_TIMEOUT: int = Field(default=30, exclude=True)
    AUDIT_ENABLED: bool = Field(default=True, exclude=True)
    AUDIT_BUFFER_SIZE: int = Field(default=100, exclude=True)
    AUDIT_FLUSH_INTERVAL: float = Field(default=5.0, exclude=True)

    opensearch_audit: OpenSearchAuditConfig = Field(default_factory=OpenSearchAuditConfig)

    @model_validator(mode="after")
    def _hydrate_opensearch_audit(self) -> "Settings":
        """Hydrate sub-model from flat env values (mirrors GitProviderConfig pattern).

        Precedence rule: if the caller explicitly passed an OpenSearchAuditConfig
        instance via ``Settings(opensearch_audit=...)``, that wins over the flat
        env vars. Otherwise the flat fields hydrate the sub-model.

        Detection: ``opensearch_audit`` differs from a fresh default-factory
        instance ⇒ caller-provided. This avoids pickling/equality fragility on
        SecretStr by checking model_dump() identity at the boundary.
        """
        default_dump = OpenSearchAuditConfig().model_dump()
        if self.opensearch_audit.model_dump() != default_dump:
            return self  # explicit sub-model — leave untouched

        self.opensearch_audit = OpenSearchAuditConfig(
            host=self.OPENSEARCH_HOST,
            user=self.OPENSEARCH_USER,
            password=self.OPENSEARCH_PASSWORD,
            verify_certs=self.OPENSEARCH_VERIFY_CERTS,
            ca_certs=self.OPENSEARCH_CA_CERTS,
            timeout=self.OPENSEARCH_TIMEOUT,
            audit_enabled=self.AUDIT_ENABLED,
            audit_buffer_size=self.AUDIT_BUFFER_SIZE,
            audit_flush_interval=self.AUDIT_FLUSH_INTERVAL,
        )
        return self
```

**Precedence rule documented in CLAUDE.md note #2**: explicit `Settings(opensearch_audit=...)` wins over flat env vars; absence of an explicit sub-model triggers flat-field hydration.

Then delete `OpenSearchSettings` class from `opensearch_integration.py` and rewire:
```python
# opensearch_integration.py
from src.config import settings  # noqa

@lru_cache
def get_settings() -> "OpenSearchAuditConfig":
    return settings.opensearch_audit
```

Note: `Settings.OPENSEARCH_URL` (docs/embedding endpoint, line 343) is **separate** and stays. Its name collision with `OPENSEARCH_HOST` is documented in CLAUDE.md (S8 note #2). Renaming `OPENSEARCH_URL` → `DOCS_SEARCH_OPENSEARCH_URL` per discovery D.7 is **OUT OF SCOPE for INFRA-1a** (would be Bug Hunt cleanup or 1b).

**Option B — namespace OpenSearchSettings with prefix**:

```python
# control-plane-api/src/opensearch/opensearch_integration.py

class OpenSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        extra="ignore",
    )
    opensearch_host: str = "https://opensearch.gostoa.dev"
    # rest unchanged but NOW these env vars are AUDIT_OPENSEARCH_HOST/etc
```

This is a **breaking change** for the chart — the chart currently sets `OPENSEARCH_HOST`, not `AUDIT_OPENSEARCH_HOST`. Implies a coordinated stoa-infra PR. **DO NOT pick Option B unless we're prepared to ship the stoa-infra chart change in lock-step**.

#### d. Tests to add

For Option A:
```python
def test_opensearch_audit_hydrated_from_flat_env(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_HOST", "https://opensearch.example.io")
    monkeypatch.setenv("AUDIT_BUFFER_SIZE", "200")
    s = Settings()
    assert s.opensearch_audit.host == "https://opensearch.example.io"
    assert s.opensearch_audit.audit_buffer_size == 200

def test_opensearch_audit_distinct_from_docs_search_url():
    """OPENSEARCH_URL (docs) and OPENSEARCH_HOST (audit) are distinct endpoints."""
    s = Settings(OPENSEARCH_URL="http://a.local", OPENSEARCH_HOST="https://b.local")
    assert s.OPENSEARCH_URL == "http://a.local"
    assert s.opensearch_audit.host == "https://b.local"

def test_opensearch_password_secret_unwrapped_for_client():
    """SecretStr round-trip — consumer code must unwrap with .get_secret_value()."""
    s = Settings(OPENSEARCH_PASSWORD="example-value")
    assert s.opensearch_audit.password.get_secret_value() == "example-value"
    # Also: repr() must not leak.
    assert "example-value" not in repr(s)

def test_explicit_opensearch_audit_submodel_wins_over_flat_env(monkeypatch):
    """Precedence rule: explicit sub-model > flat env vars."""
    monkeypatch.setenv("OPENSEARCH_HOST", "https://from-env.io")
    explicit = OpenSearchAuditConfig(host="https://explicit.io")
    s = Settings(opensearch_audit=explicit)
    assert s.opensearch_audit.host == "https://explicit.io"  # explicit wins

def test_model_dump_excludes_flat_opensearch_fields():
    """exclude=True on flat env-ingress fields prevents leak via model_dump()."""
    s = Settings(OPENSEARCH_PASSWORD="secret")
    dumped = s.model_dump()
    assert "OPENSEARCH_PASSWORD" not in dumped
    assert "OPENSEARCH_HOST" not in dumped
    # Sub-model is dumpable (with SecretStr → '**********')
    assert "opensearch_audit" in dumped
```

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Helm chart breaks (Option B) | HIGH | Don't pick Option B without stoa-infra coordination. |
| `tests/test_opensearch.py` is `--ignore`d so audit-logger regressions slip | MEDIUM | Add targeted tests in `test_config.py` instead of `test_opensearch.py`. |
| `lru_cache` in `get_settings()` keeps stale state between tests | LOW | Existing pattern; tests already use `get_settings.cache_clear()`. Honor in new tests. |
| `OPENSEARCH_PASSWORD` becomes `SecretStr` in Option A (was plain str) — code reading `.password` directly breaks | LOW | Audit consumers; unwrap with `.get_secret_value()` where needed. ~3 sites. |

---

### 2.4 — S4: `.env.example` cleanup baseline

#### a. Files to touch

- `control-plane-api/.env.example` (currently 83 lines; target ~150-200 with full coverage)
- `control-plane-ui/.env.example` (currently 35 lines; target ~50-60)
- `portal/.env.example` (currently 36 lines, broadly aligned per discovery — minor cleanup)
- `stoa-gateway/.env.example` (currently 78 lines; target ~120-130 with critical 40 keys, NOT exhaustive 165+ — explicit deferral note)
- `landing-api/.env.example` (currently 32 lines; clarify STOA_* namespace collision header note)

#### b. Behavioral preservation contract

- No code change. Pure documentation file updates.
- All entries are commented unless they require explicit value (`KEYCLOAK_URL=http://localhost:8280` for local dev). Keep developer ergonomics: copy-paste-friendly local defaults at top, prod-only knobs documented as comments.

#### c. Specific changes

**`control-plane-api/.env.example`** (per ticket scope):
- Fix line 12: `# DATABASE_POOL_SIZE=5` → `# DATABASE_POOL_SIZE=10` (matches Settings default — D.6 drift fix).
- Add new sections (commented, documented):
  - `# ── Algolia Docs Search (CAB-1327) ──`: ALGOLIA_APP_ID, ALGOLIA_SEARCH_API_KEY, ALGOLIA_INDEX_NAME, DOCS_SEARCH_ENABLED, LLMS_FULL_TXT_URL.
  - `# ── Chat Agent (CAB-286) ──`: CHAT_ENABLED, CHAT_PROVIDER_API_KEY, CHAT_GATEWAY_URL, CHAT_GATEWAY_API_KEY, CHAT_KILL_SWITCH, CHAT_TOKEN_BUDGET_DAILY, CHAT_RATE_LIMIT_*.
  - `# ── Embeddings / Semantic Docs Search (CAB-1327 P2) ──`: EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_API_KEY, EMBEDDING_DIMENSIONS, EMBEDDING_API_URL, DOCS_REINDEX_ENABLED, OPENSEARCH_URL, OPENSEARCH_DOCS_INDEX.
  - `# ── Vault (HCP) ──`: VAULT_ADDR, VAULT_TOKEN, VAULT_KUBERNETES_ROLE, VAULT_MOUNT_POINT, VAULT_ENABLED.
  - `# ── Sender-Constrained Tokens (CAB-438 RFC 8705 mTLS / RFC 9449 DPoP) ──`: SENDER_CONSTRAINED_ENABLED, SENDER_CONSTRAINED_STRATEGY, SENDER_CONSTRAINED_DPOP_MAX_CLOCK_SKEW.
  - `# ── Logging Debug (CAB-2145 prod-gated) ──`: LOG_DEBUG_AUTH_TOKENS, LOG_DEBUG_AUTH_HEADERS, LOG_DEBUG_AUTH_PAYLOAD, LOG_DEBUG_HTTP_BODY, LOG_DEBUG_HTTP_HEADERS, plus LOG_DEBUG_KAFKA_*, LOG_DEBUG_SQL_*, LOG_DEBUG_SSL_*. Comment: "These flags refuse boot in ENVIRONMENT=production (CAB-2145)."
  - `# ── OpenSearch (audit) — namespace ambiguity ──` (header): explain that `OPENSEARCH_HOST/USER/PASSWORD/VERIFY_CERTS/CA_CERTS/TIMEOUT` and `AUDIT_*` map to `Settings.opensearch_audit.*` (post Option A), distinct from `OPENSEARCH_URL` (docs/embedding endpoint). Cross-link to `CLAUDE.md` note.
- Document **deferred autogen plan** (ticket Q8 / discovery G.5.b): add a top-of-file comment: `# This file is hand-maintained. INFRA-1c will add a CI lint step that diffs keys against Settings.__fields__. Long-term: INFRA-1c will add a config dump command and CI diff (no such command exists today; do not copy-paste).`

**`control-plane-ui/.env.example`** (per ticket scope):
- Add: VITE_AWX_URL, VITE_PORTAL_MODE, VITE_GIT_PROVIDER, VITE_GIT_REPO_URL, VITE_GITLAB_URL, VITE_DATE_FORMAT, VITE_ARENA_DASHBOARD_URL, VITE_AUTH_REFRESH_TIMEOUT_MS, VITE_AVAILABLE_ENVIRONMENTS, VITE_REQUIRE_SANDBOX_CONFIRMATION, VITE_ERROR_TRACKING_ENDPOINT, VITE_API_DOCS_URL.

**`stoa-gateway/.env.example`**:
- Add critical 40 (per discovery A.5 + Section H Q-8 deferral note):
  - mTLS: `STOA_MTLS__ENABLED`, `STOA_MTLS__CA_CERT_PATH`, `STOA_MTLS__CERT_PATH`, `STOA_MTLS__KEY_PATH`, `STOA_MTLS__VERIFY_CLIENT_CERT`, `STOA_MTLS__REQUIRE_CLIENT_CERT`, `STOA_MTLS__CLIENT_CERT_BINDING_REQUIRED` (~7).
  - DPoP: `STOA_DPOP__REQUIRED`, `STOA_DPOP__MAX_CLOCK_SKEW_SECONDS`, `STOA_DPOP__NONCE_REQUIRED`, `STOA_DPOP__NONCE_TTL_SECONDS` (~4).
  - Sender constraint: `STOA_SENDER_CONSTRAINT__DPOP_REQUIRED`, `STOA_SENDER_CONSTRAINT__MTLS_REQUIRED`, `STOA_SENDER_CONSTRAINT__STRATEGY` (~3).
  - LLM router: `STOA_LLM_ROUTER__DEFAULT_STRATEGY`, `STOA_LLM_ROUTER__BUDGET_DAILY_USD`, `STOA_LLM_ROUTER__BUDGET_TENANT_DAILY_USD`, `STOA_LLM_ROUTER__FALLBACK_PROVIDER`, `STOA_LLM_ROUTER__CACHE_ENABLED` (~5).
  - API proxy: `STOA_API_PROXY__ENABLED`, `STOA_API_PROXY__LINEAR_API_KEY`, `STOA_API_PROXY__GITHUB_TOKEN`, `STOA_API_PROXY__SLACK_BOT_TOKEN` (~4 — 4 per backend).
  - Core knobs: `STOA_LOG_LEVEL`, `STOA_LOG_FORMAT`, `STOA_ENVIRONMENT`, `STOA_INSTANCE_NAME`, `STOA_HOST`, `STOA_PORT`, `STOA_GATEWAY_MODE`, `STOA_AUTO_REGISTER`, `STOA_OTEL_ENDPOINT`, `STOA_OTEL_SAMPLE_RATE`, `STOA_OTEL_ENABLED`, `STOA_KAFKA_BROKERS`, `STOA_KAFKA_METERING_TOPIC`, `STOA_KAFKA_ERRORS_TOPIC`, `STOA_KEYCLOAK_URL`, `STOA_KEYCLOAK_INTERNAL_URL`, `STOA_KEYCLOAK_REALM`, `STOA_KEYCLOAK_CLIENT_ID`, `STOA_KEYCLOAK_CLIENT_SECRET`, `STOA_KEYCLOAK_ADMIN_PASSWORD`, `STOA_GIT_PROVIDER`, `STOA_GITHUB_TOKEN`, `STOA_GITHUB_ORG`, `STOA_GITHUB_CATALOG_REPO`, `STOA_POLICY_PATH` (~25).
- Add header comment: `# This file documents ~40 of the most critical STOA_* keys. Exhaustive coverage (165+ keys in src/config.rs) deferred to autogen tooling (INFRA-1c per Q8). For full reference see stoa-gateway/src/config.rs and src/config/*.rs.`

**`landing-api/.env.example`**:
- Add file header: `# WARNING: landing-api uses STOA_* prefix that COLLIDES with stoa-gateway STOA_* prefix. # Do NOT deploy landing-api in the same K8s namespace as stoa-gateway without explicit env scoping. # See INFRA-1-DISCOVERY.md A.5 (file: landing-api/.env.example collision note).`

#### d. Tests to add

None — `.env.example` files are not loaded by pytest. The CI lint to diff against `Settings.__fields__` is **deferred to INFRA-1c** (Q8). Phase 1a is the baseline.

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Developers paste outdated value from old `.env.example` and break local | NEGLIGIBLE | Pure docs improvement. |
| `.env.example` re-drifts after merge (no CI guard until 1c) | LOW | Acceptable per Q8. Track in 1c ticket scope. |

---

### 2.5 — S5: Pydantic validators tightening

#### a. Files to touch

- `control-plane-api/src/config.py:389` (`LOG_FORMAT: str = "json"`)
- `control-plane-api/src/config.py:113, 492, 600, 626, 644` (ENVIRONMENT validators)

#### b. Behavioral preservation contract

- `LOG_FORMAT` Literal tightening: must accept exactly the values currently used in code/docs (`"json"`, `"text"`).
- `ENVIRONMENT` validators:
  - **Default behavior preserved**: `ENVIRONMENT=production` continues to trigger sensitive-debug-flag gate, auth-bypass gate, git-provider validation.
  - **New: `ENVIRONMENT=prod` accepted as equivalent** (per ticket scope — gateway uses `prod`, cp-api uses `production`). All four `== "production"` checks become `in ("production", "prod")` checks.

#### c. Specific changes

**LOG_FORMAT**:
```python
# Before: LOG_FORMAT: str = "json"  # json, text
# After:
LOG_FORMAT: Literal["json", "text"] = "json"
```

**ENVIRONMENT** — pick ONE of two patterns:

**Pattern A (preserve string field, narrow normalization)** — strip whitespace and ONLY remap the exact `prod` token to `production`. Do NOT lowercase other values; preserve `Staging`, `dev`, etc. as the caller wrote them (matches BH-8 mitigation: avoid silently transforming case of unrelated values):
```python
@field_validator("ENVIRONMENT", mode="before")
@classmethod
def _normalize_environment(cls, v: object) -> object:
    """Accept 'prod' as equivalent to 'production' (CAB-2199, gateway uses 'prod').

    Surgical mapping — does NOT lowercase other values. `Staging`, `PRODUCTION`,
    `dev` are passed through untouched (preserves caller spelling for any
    downstream consumer that case-discriminates).
    """
    if isinstance(v, str):
        stripped = v.strip()
        if stripped == "prod":
            return "production"
        return stripped
    return v
```

This funnels exactly `prod` into the canonical `production` string, so existing `== "production"` checks just work for both spellings. Other values pass through. **PREFERRED** — minimum diff, no case-fold surprise.

**Pattern B (Literal + helper)**:
```python
ENVIRONMENT: Literal["dev", "staging", "production", "prod"] = "production"

@property
def is_production(self) -> bool:
    return self.ENVIRONMENT in ("production", "prod")
```
Then refactor 4 sites from `== "production"` to `is_production`. Larger diff, more invasive.

**Recommend Pattern A** — pinned to Section 3 #4.

#### d. Tests to add

```python
def test_log_format_literal_rejects_invalid():
    with pytest.raises(ValidationError):
        Settings(LOG_FORMAT="yaml")

def test_environment_prod_normalized_to_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    s = Settings()
    assert s.ENVIRONMENT == "production"
    # sensitive-debug gates trigger on either spelling
    monkeypatch.setenv("LOG_DEBUG_AUTH_TOKENS", "true")
    with pytest.raises(ValueError, match="ENVIRONMENT=production"):
        Settings()

def test_environment_production_unchanged(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = Settings()
    assert s.ENVIRONMENT == "production"
```

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Some test sets `ENVIRONMENT="prod"` and asserts non-prod behavior (unlikely, but possible) | LOW | grep `ENVIRONMENT.*prod` in tests; expected hit count: 0–2 false positives. |
| `LOG_FORMAT="text"` is the only valid alt; existing prod sets `"json"` | NEGLIGIBLE | Verify Helm chart values: cp-api chart `env.LOG_FORMAT` likely absent, defaults to `json`. |

---

### 2.6 — S6: `STOA_SNAPSHOTS_*` rename Case A (alias + boot-fail-on-conflict + deprecation log + Prometheus metric)

#### a. Files to touch

- `control-plane-api/src/features/error_snapshots/config.py:24-29` (env_prefix change, alias logic)
- `control-plane-api/src/features/error_snapshots/__init__.py` (no change expected; verify)
- `control-plane-api/tests/test_snapshot_config.py:29-34` (env vars in test fixture — must use new prefix OR test alias path)
- `control-plane-api/tests/test_snapshot_storage_ops.py:15-20, 297, 319-320` (same)
- New: `control-plane-api/tests/test_snapshot_config_alias.py` (regression guard for alias + conflict + deprecation log + metric).
- `control-plane-api/.env.example` (S4 coupling — snapshot section).
- `control-plane-api/CLAUDE.md` (S8 note #3).

#### b. Behavioral preservation contract

- **Old prefix `STOA_SNAPSHOTS_*` keeps working** for at least 1 release (per Q7 alias-friendly decision).
- New canonical prefix is `STOA_API_SNAPSHOT_*` (singular SNAPSHOT, scoped by `_API_` to disambiguate from Rust gateway `STOA_SNAPSHOT_*` — see Section 3 #3 for naming arbitrage).
- Boot fails (raises) if BOTH old and new prefix env vars are set with different values (per ticket AC).
- Boot succeeds (with deprecation log) if only old prefix set.
- Boot succeeds (no log, no metric) if only new prefix set.
- Boot succeeds (no log, no metric, no error) if both set with matching values.

#### c. Specific changes

> **Implementation code extracted to `docs/infra/INFRA-1a-IMPL-S6.md`** (revision v3, Council Stage 2 adjustments #1+#2 secret masking + #3 plan-length trim). The companion file holds: full `AliasChoices` field declarations, `_detect_conflicts_and_emit_deprecation` validator, `_read_dotenv` helper, `_is_secret_env_key`/`_redact_value` masking helpers, Prometheus Counter declaration, `_METRIC_EMITTED_KEYS` one-shot guard.

**Summary of the change** (full code in companion):

- **Naming**: rename Python `env_prefix` from `STOA_SNAPSHOTS_` (plural) to `STOA_API_SNAPSHOT_` (singular + `_API_` scope, unambiguous in `kubectl describe pod`). **Decision pinned to Section 3 #3**.
- **Alias surface**: per-field `validation_alias=AliasChoices(NEW, OLD)` so the legacy prefix continues to resolve from process env, dotenv file, and pydantic-settings secrets sources — not just `os.environ`.
- **Conflict scanner**: `model_validator(mode="before")` reads BOTH `os.environ` AND the configured dotenv file. Any suffix with distinct values across old/new prefix raises `ValueError` with **secret-aware redaction** (Council Stage 2 #1+#2): keys matching `*SECRET*`/`*KEY*`/`*TOKEN*`/`*PASSWORD*` (case-insensitive substring) have their VALUES replaced with `<REDACTED>` in the error message. Key NAMES remain visible (operator debugging).
- **Deprecation log**: `WARNING` line emits sorted KEYS only, never values. Masking helper kept available as defence-in-depth for any future log additions.
- **Prometheus metric**: `Counter("stoa_deprecated_config_used", labelnames=["name"])` — `client_python` auto-appends `_total` at exposition. Boot-only; one-shot per key per process via `_METRIC_EMITTED_KEYS` set + `Lock`.
- **Schema metadata**: `DEPRECATED_PREFIX_ALIASES: ClassVar[dict[str, str]] = {STOA_SNAPSHOTS_: STOA_API_SNAPSHOT_}` for INFRA-1c CI gate consumption.

**Council Stage 2 secret-masking heuristic** (folded into companion file):

```python
_SECRET_NAME_TOKENS = ("SECRET", "KEY", "TOKEN", "PASSWORD")

def _is_secret_env_key(env_key: str) -> bool:
    upper = env_key.upper()
    return any(token in upper for token in _SECRET_NAME_TOKENS)
```

Conservative substring match — false positives (mask a non-secret value) are harmless; false negatives (leak a secret) are unacceptable. The `KEYRING` false positive is acknowledged in the companion file.

#### d. Tests to add

> **Test corpus extracted to `docs/infra/INFRA-1a-IMPL-S6.md`**. Summary: **11 tests** in `control-plane-api/tests/test_snapshot_config_alias.py` covering: new prefix resolution, legacy alias deprecation log + metric, boot-fail-on-conflict (env & dotenv), one-shot Counter guard, secret-value redaction (regression for Council #1+#2), non-secret value visibility (counter-test), `_is_secret_env_key` direct unit test. Plus migration of existing `test_snapshot_config.py` and `test_snapshot_storage_ops.py` to the new prefix with one `test_legacy_*` regression case per file using the old prefix.

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| `lru_cache` masks alias resolution between tests | MEDIUM | Tests must call `get_snapshot_settings.cache_clear()` (existing pattern in repo). |
| `DEPRECATED_CONFIG_USED` Counter registered at module import: re-import in tests fails | MEDIUM | `prometheus_client` registry is a singleton; existing test patterns import metric module once per session — verify no `unregister_after_session` flake. |
| Boot-fail-on-conflict breaks deployments where ops set BOTH prefixes after a partial migration | MEDIUM | Document migration path in CLAUDE.md note #3: "Set new prefix only OR keep both with matching values." |
| Rust `STOA_SNAPSHOT_*` (singular) collision: an operator setting `STOA_SNAPSHOT_RETENTION_DAYS=7` (intending Rust) also matches an env var that is *not* the legacy Python `STOA_SNAPSHOTS_*` — but new Python prefix `STOA_API_SNAPSHOT_*` is unambiguous. **No conflict.** | LOW | Naming choice with `_API_` prefix prevents this. |
| Legacy alias surface (alias logic) burned-in for "1 release" — when does it sunset? Per memory `feedback_no_schedule_arbitrary_timers.md`, sunset is on evidence-of-non-use, not calendar. | LOW | Track sunset on a Linear ticket (open after PR-E ships): "Remove STOA_SNAPSHOTS_* alias when DEPRECATED_CONFIG_USED metric reads 0 for 30 consecutive days in prod". |
| Prometheus metric name collides with existing metric | LOW | Prefix `stoa_deprecated_config_used_total` is unique; verify no existing in cp-api. |

---

### 2.7 — S7: Multi-env-ready rule application (Q6 — no new hardcoded `gostoa.dev` outside `BASE_DOMAIN`)

#### a. Files to touch

- All files touched by S2/S4/S6 (ride-along audit).
- `control-plane-api/src/config.py` — verify no remaining `gostoa.dev` outside line 117 default.
- `control-plane-api/.env.example` — verify all derived URLs are commented (defaults shown but commented out).

#### b. Behavioral preservation contract

- No code change expected — this is a lint/audit pass on changes from S2/S4/S6.
- If any new `gostoa.dev` literal slipped into code in S2/S4/S6 PRs, surface and replace with `BASE_DOMAIN` derivation BEFORE that PR ships.

#### c. Specific changes

Pre-merge grep for each PR (B/C/D/E):
```bash
git diff origin/main...HEAD -- control-plane-api/src/ | grep -i "gostoa.dev"
```
Expected: only `BASE_DOMAIN: str = "gostoa.dev"` default (line ~117). Any other `gostoa.dev` in cp-api src must be a derived URL from `BASE_DOMAIN`, not a literal.

This audit becomes a **PR template checkbox**: "[ ] No new `gostoa.dev` literal in src/ outside `BASE_DOMAIN` default (Q6 multi-env ready)".

#### d. Tests to add

Optionally (cheap regression guard): a CI grep added in INFRA-1c, NOT in 1a (this is a lint, deferred per Q8 pattern). Phase 1a only enforces it manually.

#### e. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Audit forgotten on one PR | LOW | Author checklist + self-review pre-PR. |

---

### 2.8 — S8: Documentation updates

#### a. Files to touch

- `control-plane-api/CLAUDE.md` (3 new notes appended at bottom, one per major change).

#### b. Behavioral preservation contract

- Pure documentation. No code change.
- Notes are concise (5-15 lines each per CLAUDE.md "rules binaires" style).

#### c. Specific changes

**Note #1 — `_BASE_DOMAIN` Pydantic load-time freezing fix (S2)**:

```markdown
## BASE_DOMAIN — derived URLs recompute on Settings instantiation

Per CAB-2199 / INFRA-1a, the module-level `_BASE_DOMAIN = os.getenv(...)` was
removed. `BASE_DOMAIN` is now read by Pydantic at instantiation, and derived
URLs (`KEYCLOAK_URL`, `GATEWAY_URL`, `ARGOCD_URL`, `GRAFANA_URL`,
`PROMETHEUS_URL`, `LOGS_URL`, `GATEWAY_ADMIN_PROXY_URL`, `ARGOCD_EXTERNAL_URL`,
`CORS_ORIGINS`) are computed in a `@model_validator(mode="after")` from the
resolved `BASE_DOMAIN` value.

Implication for tests: `Settings(BASE_DOMAIN="other.tld").KEYCLOAK_URL` now
returns `"https://auth.other.tld"`. Previously frozen at import time at
`"https://auth.gostoa.dev"` — silent test isolation bug.

Setting an explicit URL (e.g. `KEYCLOAK_URL="https://kc.foo.io"`) wins over
the BASE_DOMAIN derivation. Empty default `""` is the sentinel for "derive me".

If you add a new derived URL field, register it in the validator. Do NOT add
new `gostoa.dev` literals (Q6 multi-env ready).
```

**Note #2 — `OpenSearchSettings` consolidation (S3)**:

```markdown
## OpenSearch — audit endpoint vs docs/embedding endpoint

Per CAB-2199 / INFRA-1a (Option A), `OpenSearchSettings` (formerly in
`opensearch/opensearch_integration.py`) is now `Settings.opensearch_audit`
(sub-model `OpenSearchAuditConfig`, hydrated from flat env vars
`OPENSEARCH_HOST/USER/PASSWORD/VERIFY_CERTS/CA_CERTS/TIMEOUT` and `AUDIT_*`).

This is the audit-logger / search-service endpoint (currently
`https://opensearch.gostoa.dev` in prod via Helm chart `env.OPENSEARCH_HOST`).

`Settings.OPENSEARCH_URL` (default `http://opensearch.stoa-system.svc...:9200`)
is a SEPARATE field for docs/embedding search. The two endpoints can — and in
prod often do — point at different OpenSearch clusters. Do not conflate.

Long-term: rename `OPENSEARCH_URL` → `DOCS_SEARCH_OPENSEARCH_URL` (deferred
to INFRA-1b / Bug Hunt). Phase 1a does not change this.
```

**Note #3 — `STOA_SNAPSHOTS_*` rename + alias (S6)**:

```markdown
## STOA_API_SNAPSHOT_* — error snapshot config (formerly STOA_SNAPSHOTS_*)

Per CAB-2199 / INFRA-1a, `SnapshotSettings.env_prefix` was renamed from
`STOA_SNAPSHOTS_` (plural) to `STOA_API_SNAPSHOT_` (singular + `_API_`
namespace). The `_API_` prefix disambiguates from the Rust gateway
`STOA_SNAPSHOT_*` (singular, in-process ring buffer) which is unrelated.

The legacy `STOA_SNAPSHOTS_*` prefix is honored as an alias for one release
with:
- a `WARNING`-level deprecation log line at boot,
- a Prometheus metric `stoa_deprecated_config_used_total{name="STOA_SNAPSHOTS_*"}`,
- a boot failure if both old and new prefixes are set with different values.

Migration: rename ops env vars from `STOA_SNAPSHOTS_*` to `STOA_API_SNAPSHOT_*`.
Once the metric reads 0 for 30 consecutive days in prod, the alias can be
removed (tracked on a sunset Linear ticket; per HLFH policy, removals are
gated on evidence of non-use, not calendar).
```

#### d. Tests to add

None.

#### e. Risks & mitigations

None — pure documentation.

---

## Section 3 — Decision points to escalate (Christophe arbitrates BEFORE Phase 2)

These decisions block Phase 2 implementation. Each lists options + recommendation + critères de choix.

### 3.1 — Decision Point #1: `OpenSearchSettings` consolidation — Option A or Option B?

**Context**: Discovery E.4 + ticket scope. Two options:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** | Move OpenSearchSettings INTO main `Settings` as `OpenSearchAuditConfig` sub-model (mirrors `GitProviderConfig`). 9 flat env vars hydrated to sub-model by validator. | Single Pydantic class; same env var names (no chart change); pattern consistency with git provider. | Adds 9 fields with `exclude=True` to main Settings (verbosity); existing `OpenSearchService` consumer code rewires to `settings.opensearch_audit`. |
| **B** | Rename `OpenSearchSettings.opensearch_host` etc. with `env_prefix="AUDIT_"`. New env vars `AUDIT_OPENSEARCH_HOST`, `AUDIT_OPENSEARCH_USER`, etc. | Clean namespace separation; stays in `opensearch_integration.py`. | **Breaking change for chart**: `stoa-infra/charts/control-plane-api/values.yaml` currently sets `OPENSEARCH_HOST` — would need lock-step stoa-infra PR. |

**Recommendation**: **Option A**. Critères: keep stoa-infra unchanged in 1a (1b owns chart refactors), pattern consistency with `GitProviderConfig`, single Settings class for grep-ability.

**Décide**: ☐ A   ☐ B   ☐ Other:_____

### 3.2 — Decision Point #2: `BASE_DOMAIN` derived URLs — `@property` recompute or `model_validator(mode="before")` resolve?

**Context**: Section 2.2.c. Two patterns to fix the freezing:

| Pattern | Description | Pros | Cons |
|---------|-------------|------|------|
| **Property** | Convert 9 fields to `Optional[str] = None`; add `@property` per derived URL. | Lazily computed; field types reflect nullable nature. | 9 properties × signature change = 24 importer churn; `model_dump()` exposes `None` for unset. |
| **Validator (`mode="before"`, `setdefault`)** | Keep fields `str = ""`; add ONE `@model_validator(mode="before")` that injects derived URLs for fields ABSENT from input dict (presence-based, not truthiness-based). | Smaller diff; types unchanged; `model_dump()` returns resolved strings (consumers transparent); explicit empty-string overrides preserved (caller intent honored). | Resolution at instantiation, not lazy (negligible perf cost). |

**Recommendation**: **Validator (`mode="before"`)**. Critères: minimum diff, zero consumer churn, single-validator pattern matches `_hydrate_and_validate_git`, presence-based dispatch avoids the `if not field` truthiness trap.

**Décide**: ☐ Property   ☐ Validator (mode="before")   ☐ Other:_____

### 3.3 — Decision Point #3: `STOA_SNAPSHOTS_*` new prefix name?

**Context**: Section 2.6.c. Rust uses `STOA_SNAPSHOT_*` (singular, ring buffer). Python is currently `STOA_SNAPSHOTS_*` (plural, error snapshots feature).

| Option | New Python prefix | Pros | Cons |
|--------|--------------------|------|------|
| **A1** | `STOA_API_SNAPSHOT_*` (singular + `_API_` scope) | Unambiguous in `kubectl describe`; aligned with Rust singular; "API" namespace clear. | Longer name (4 extra chars). |
| **A2** | `STOA_API_SNAPSHOTS_*` (plural, less divergent from current) | Smaller migration delta. | Plural mismatches Rust singular; `_API_` scope still needed. |
| **B** | Keep `STOA_SNAPSHOTS_*` (do nothing) | No migration. | Doesn't address Q7 disambiguation goal; CAB-2199 explicitly asks for rename Case A. |

**Recommendation**: **A1** (`STOA_API_SNAPSHOT_*`). Critères: maximum disambiguation, scope-clear in ops dashboards, plural/singular consistency across stack.

**Décide**: ☐ A1   ☐ A2   ☐ B   ☐ Other:_____

### 3.4 — Decision Point #4: ENVIRONMENT validator pattern — normalize-to-`production` or extend Literal?

**Context**: Section 2.5.c. Gateway uses `prod`, cp-api uses `production`. Ticket asks for consistency.

| Pattern | Description | Pros | Cons |
|---------|-------------|------|------|
| **A — Normalize** | `field_validator(mode="before")` maps `prod → production`. All existing `== "production"` checks unchanged. | 1 validator, 4 lines; zero downstream churn. | `s.ENVIRONMENT` is always canonical `"production"` — caller cannot tell which spelling was set. |
| **B — Literal + helper** | `Literal["dev","staging","production","prod"]`; replace `== "production"` with `is_production` property. | Both spellings observable. | 4 sites refactor; broader diff. |

**Recommendation**: **A**. Critères: minimum diff, no observable difference for ops (canonical name everywhere).

**Décide**: ☐ A   ☐ B   ☐ Other:_____

### 3.5 — Decision Point #5: per-directory `<svc>/k8s/` audit — delete sibling files (deployment/service/ingress/hpa/pdb) in this PR or defer?

**Context**: Section 2.1. CAB-2199 scope mentions "Delete other monorepo `<svc>/k8s/*.yaml` files after per-directory audit". 19 candidate files.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Delete all 21 in PR-A** | After ArgoCD audit, `git rm` everything in `<svc>/k8s/`. | Single cleanup pass; smaller blast radius if audit confirms dead. | Larger PR; harder to revert one file vs many. |
| **B — Delete configmap.yaml only in 1a; defer rest to a follow-up "k8s-dir cleanup" ticket** | Ship PR-A with the 2 confirmed dead `configmap.yaml`s only. Open a follow-up Linear ticket for the 19 sibling files. | Tighter scope per PR; per-file audit easier. | Two passes for one logical cleanup. |
| **C — Delete configmap.yaml + audit each `k8s/` dir for the chart-template equivalent in stoa-infra; delete only when 1:1 superseded** | Per-file evidence: `stoa-infra/charts/<svc>/templates/deployment.yaml` exists ⇒ `<svc>/k8s/deployment.yaml` deletable. | Strongest evidence trail. | Most time-consuming. |

**Recommendation**: **B**. Critères: tight 1a scope, evidence-driven (each `k8s/` dir gets its own PR with explicit audit). Open follow-up after 1a ships.

**Décide**: ☐ A   ☐ B   ☐ C   ☐ Other:_____

### 3.6 — Decision Point #6: `.env.example` `gateway/` scope — 40 critical keys or full 165+?

**Context**: Section 2.4.c. Ticket scope says "Don't try to be exhaustive. Document the most critical ~40."

| Option | Description |
|--------|-------------|
| **A** | Document critical 40 (mtls, dpop, sender_constraint, llm_router, api_proxy, core knobs). Add header comment deferring exhaustive coverage to autogen tooling (Q8 / INFRA-1c). |
| **B** | Document all 165+ keys. |

**Recommendation**: **A** per ticket scope explicit guidance.

**Décide**: ☐ A   ☐ B   ☐ Other:_____

### 3.7 — Decision Point #7: Do we open a sunset Linear ticket for `STOA_SNAPSHOTS_*` alias removal during 1a?

**Context**: Section 2.6.e + memory `feedback_no_schedule_arbitrary_timers.md` (no calendar-based scheduling; sunset on evidence of non-use).

| Option | Description |
|--------|-------------|
| **A** | Open follow-up Linear ticket "Remove STOA_SNAPSHOTS_* alias once metric reads 0 for 30 consecutive days" before PR-E ships. Tracker, no auto-execution. |
| **B** | Defer ticket creation; documentation in CLAUDE.md is sufficient until evidence is needed. |

**Recommendation**: **A**. Critères: explicit follow-up tracking matches HLFH "extract is the moment to spot divergences" pattern (memory `feedback_extract_spot_divergences.md`).

**Décide**: ☐ A   ☐ B   ☐ Other:_____

---

## Section 4 — Bug Hunt seed (HEG-PAT-020 §4.4)

Latent bugs surfaced during planning. **Phase 1 preserves behavior — these are NOT fixed in 1a**, only documented for Phase 2 Bug Hunt.

| ID | Localisation | Symptôme | Sévérité hint | Pre-existing or surfaced by rewrite? |
|----|--------------|----------|---------------|--------------------------------------|
| BH-1 | `control-plane-api/src/config.py:148-151` | `KEYCLOAK_ADMIN_CLIENT_SECRET` uses `os.getenv` at class-definition time (load-time freezing, same shape as `_BASE_DOMAIN`). Setting `KEYCLOAK_ADMIN_PASSWORD` env var after Python import has no effect. | P1 (security: admin client) | Pre-existing, parallel to S2 fix. Out of 1a scope; document and fix in Phase 2 BH. |
| BH-2 | `control-plane-api/src/config.py:343` (`OPENSEARCH_URL` field) vs `OpenSearchSettings.opensearch_host` (E.4 + D.7 in discovery) | Two distinct fields named almost identically point at different defaults (`http://...:9200` vs `https://opensearch.gostoa.dev`). Maintainer confusion guaranteed. | P2 (developer experience, no functional bug today) | Pre-existing. Discovery flagged rename to `DOCS_SEARCH_OPENSEARCH_URL`. Out of 1a; Phase 2 BH. |
| BH-3 | `control-plane-api/.env.example:36-39` line `OPENSEARCH_HOST=https://localhost:9200` | Existing `.env.example` documents `https://localhost:9200` for OpenSearch but `OpenSearchSettings.opensearch_host` default is `https://opensearch.gostoa.dev`. Drift. | P3 (docs only) | Pre-existing. Fixed inline by S4 (within 1a scope). |
| BH-4 | `stoa-infra/charts/control-plane-api/templates/deployment.yaml:76-77` `MCP_GATEWAY_URL` hardcode points at retired `mcp-gateway` Service | Per discovery C.2, retired Feb 2026. Hardcode bypasses Settings default. | P0 (chat routing breaks if cluster has no `mcp-gateway` Service alias). **HIGH RISK**. | Pre-existing. **OUT OF 1a SCOPE** (stoa-infra change → 1b). **HARD GATE for Phase 1a**: a dedicated Linear follow-up ticket (owner + priority + linkage to INFRA-1b) MUST exist BEFORE Phase 2 starts — see §7.1 DoD. |
| BH-5 | `control-plane-api/src/config.py:324` `ALGOLIA_SEARCH_API_KEY: str = "<32-char-hex-redacted>"` (Algolia public search-only key hardcoded as default in source) | Public search-only key hardcoded as default in source. Not a secret per se (Algolia search keys are public), but this is a code smell — defaults should not embed third-party identifiers. Multi-tenant SaaS risk if shipped to a client who happens to use Algolia themselves. | P3 (smell, no functional bug; rotate-by-design via env var) | Pre-existing. Phase 2 BH (or earlier client-anonymization sweep). The exact value is intentionally redacted from this doc to avoid Gitleaks pattern flagging — see `control-plane-api/src/config.py:324` in main for the literal. |
| BH-6 | `control-plane-api/src/config.py:227` `ARGOCD_PLATFORM_APPS: str = "stoa-gateway,control-plane-api,control-plane-ui,stoa-portal"` | Hardcoded list of apps — drifts as the platform adds/removes services. Not URL-derivation but related "fixed-string default" anti-pattern. | P3 (drift) | Pre-existing. Phase 2 BH. |
| BH-7 | `LOG_LEVEL: str = "INFO"` (no Literal validator, accepts any string) | `LOG_LEVEL=DBG` (typo) silently accepted; behavior at runtime depends on stdlib `logging` (likely sets level to nothing useful). Not in CAB-2199 scope (only LOG_FORMAT is). | P2 (config typos masked) | Pre-existing. Add `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]` in Phase 2 BH. |
| BH-8 | `_normalize_environment` (proposed in S5) maps `prod → production`. If a future test sets `ENVIRONMENT="staging"` and reads `s.ENVIRONMENT` expecting case-sensitive value, the new lower-casing in the validator could surprise. | Behavior change risk in S5 itself: `.lower()` normalization in the new validator. | P3 (behavior expansion) | **Surfaced by S5 rewrite**. Mitigated by: only mapping `prod → production`; pass-through for all other strings (no case fold). Verified in Pattern A spec above. |
| BH-9 | Tests using `monkeypatch.setenv("BASE_DOMAIN", ...)` BEFORE module import vs `Settings(BASE_DOMAIN=...)` after import yield different KEYCLOAK_URL today. Some test in repo may rely on the bug-frozen behavior. | After S2 fix: test that asserts `KEYCLOAK_URL == "https://auth.gostoa.dev"` while passing a `BASE_DOMAIN` override may break. | P2 (test flake on fix landing) | **Surfaced by S2 rewrite**. Mitigation: search for `BASE_DOMAIN` in test fixtures BEFORE PR-B opens; update or replace as needed. |
| BH-10 | `control-plane-api/src/config.py:361-367` `CORS_ORIGINS` default uses `_BASE_DOMAIN` 6 times. Validator pattern (S2) handles via `_derive_urls_from_base_domain` validator. But operator overriding `CORS_ORIGINS` env var to `https://console.example.io` (single origin) loses `localhost:3000` and `console.stoa.local` defaults. Not new in S2 — pre-existing semantics. | Pre-existing UX trap: setting CORS_ORIGINS replaces, doesn't merge. | P3 (UX, doc note in CLAUDE.md) | Pre-existing. Phase 2 BH. |

**Total**: 10 bugs flagged. 3 are pre-existing P0/P1 candidates (BH-1, BH-4 — chart, out of 1a scope). 7 are P2/P3 (developer experience / docs).

---

## Section 5 — Test strategy

### 5.1 — Pre-flight `pytest` baseline

Before any PR opens:
```bash
cd control-plane-api
pip install -r requirements.txt
pip install -e .[dev]
pytest --cov=src --cov-fail-under=70 --ignore=tests/test_opensearch.py -q 2>&1 | tee /tmp/pytest-baseline.log
```

Capture coverage % and pass/fail. PR-A through PR-E **must not regress this baseline**. Per CLAUDE.md: "Coverage cp-api ≥70%. Jamais descendre."

### 5.2 — New tests per PR

| PR | New tests | File |
|----|-----------|------|
| PR-A | None (deletion only) | — |
| PR-B (S2) | 5+ tests for BASE_DOMAIN derivation | `tests/test_config_base_domain_derivation.py` |
| PR-C (S3) | 2-3 tests for OpenSearchSettings consolidation (Option A: hydration; B: prefix) | `tests/test_config_opensearch_consolidation.py` |
| PR-D (S5) | 3 tests for LOG_FORMAT Literal + ENVIRONMENT normalization | `tests/test_config_validators.py` |
| PR-E (S6) | 5 tests for STOA_API_SNAPSHOT_* alias + conflict + log + metric | `tests/test_snapshot_config_alias.py` |

Plus: update existing `test_snapshot_config.py` and `test_snapshot_storage_ops.py` to use new prefix (default), with one regression case per file using the legacy prefix.

**Test count delta**: +15 tests, ~0 deletions.

### 5.3 — Coverage delta expected

- S2: +3-5% on `config.py` (validator path covered).
- S5: +1% on `config.py` (Literal + normalize validator).
- S6: +2-4% on `features/error_snapshots/config.py` (alias + conflict path).
- Total: **+6-10% net positive**, well above the 70% floor.

### 5.4 — Tests potentially impacted

Pre-merge audit per PR:
```bash
grep -rn "BASE_DOMAIN\|KEYCLOAK_URL\|ARGOCD_URL\|GRAFANA_URL\|PROMETHEUS_URL\|GATEWAY_URL\|LOGS_URL\|CORS_ORIGINS" control-plane-api/tests/ | wc -l
```
Expected hits: ~20-40. Each must be reviewed: does the test rely on the frozen-URL bug? If yes, BH-9 applies.

```bash
grep -rn "STOA_SNAPSHOTS_\|STOA_API_SNAPSHOT_" control-plane-api/tests/ | wc -l
```
Expected hits: ~10 (only `test_snapshot_*.py` files per current grep). All updated in PR-E.

```bash
grep -rn "OpenSearchSettings\|opensearch_host\|opensearch_user" control-plane-api/ --include="*.py" | wc -l
```
Expected hits: ~10. All updated in PR-C (Option A) or 2-3 sites only (Option B).

---

## Section 6 — Rollback strategy

### 6.1 — Per-PR rollback

| PR | Rollback method | Time-to-rollback | Side effects |
|----|------------------|------------------|--------------|
| PR-A (k8s deletion) | `git revert <sha>` — restores deleted files | ~30s | None (files were dead). |
| PR-B (S2 BASE_DOMAIN) | `git revert <sha>` — restores `_BASE_DOMAIN` module-level + frozen URL defaults. | ~30s | Tests added in PR-B fail post-revert; remove via revert as well (single revert handles both code + tests). |
| PR-C (S3 OpenSearch) | `git revert <sha>` — restores `OpenSearchSettings` standalone class. | ~30s | If chart was already updated to new env var names (Option B), chart must rollback in lock-step (Option A: no chart change). |
| PR-D (S5 + S4 baseline) | `git revert <sha>` — restores `LOG_FORMAT: str` and old `.env.example`. | ~30s | None. |
| PR-E (S6 SNAPSHOTS rename) | `git revert <sha>` — restores `STOA_SNAPSHOTS_*` prefix. | ~30s | Ops env vars set to new prefix `STOA_API_SNAPSHOT_*` revert to ineffective. **Operational coordination required** — ops MUST renamed back BEFORE rollback PR merges. |

### 6.2 — Feature flags / backward-compat shims during transition

- **S2**: no flag. The validator is the always-on path. Empty default `""` sentinel is the migration aid (explicit env var override paths preserved).
- **S3**: no flag (Option A is structural Pydantic refactor; Option B is breaking).
- **S5**: no flag. Literal tightening is permanent at PR merge.
- **S6**: **the alias IS the shim**. Old prefix continues to work for 1+ release. Sunset on metric evidence (Section 3 #7).

### 6.3 — Post-deploy verification

After PR-E ships to prod, verify in OVH cluster:
```bash
kubectl logs -n stoa-system <cp-api-pod> | grep "Deprecated config prefix STOA_SNAPSHOTS_"
# Expected: 0 lines if prod env was already updated, OR N lines (N = number of snapshot env vars)
# if prod is still on legacy prefix.

curl -s https://api.gostoa.dev/metrics | grep stoa_deprecated_config_used
# Expected: stoa_deprecated_config_used_total{name="STOA_SNAPSHOTS_*"} <count>
```

If count > 0: open follow-up Linear ticket to rename prod env vars (manual stoa-infra Helm values change in 1b, or coordinate with ExternalSecret refresh).

---

## Section 7 — Definition of Done

### 7.1 — Phase 1a-specific (this plan)

- [ ] Plan file `docs/infra/INFRA-1a-PLAN.md` committed on `refactor/infra-1a-phase-1-plan` branch.
- [ ] Plan reviewed and approved by Christophe.
- [ ] **All 7 Decision Points in Section 3 arbitrated** (☐ → ☑).
- [ ] Council validation (HEG quality gate) for INFRA-1a — Phase 1 plan, BEFORE Phase 2 implementation kickoff. Per CLAUDE.md: HIGH impact (16+) requires Council pass at ≥8.0/10.
- [ ] **BH-4 follow-up Linear ticket created** (owner, priority, linked to INFRA-1b) — a P0 surfaced during planning cannot remain a Bug Hunt seed entry alone. Required before Phase 2 starts to avoid a Council "P0 found, refactor proceeds without follow-up" reject.
- [ ] Phase 2 starts only after Section 3 + Council + BH-4 ticket are GREEN.

### 7.2 — Ticket CAB-2199 ACs (forwarded to Phase 2 PRs)

- [ ] Dead `<svc>/k8s/configmap.yaml` deleted (post-ArgoCD audit) — **PR-A**
- [ ] `_BASE_DOMAIN` derived URLs recompute on Settings instantiation (test added) — **PR-B**
- [ ] OpenSearchSettings consolidated (decision documented in commit) — **PR-C**
- [ ] `cp-api/.env.example` aligned with current Settings (no drift on listed fields) — **PR-D**
- [ ] `cp-ui/.env.example` includes top 30 VITE_* keys actually used — **PR-D**
- [ ] `LOG_FORMAT: Literal[...]` enforced in Pydantic — **PR-D**
- [ ] `STOA_SNAPSHOTS_*` rename with alias + deprecation log + Prometheus metric implemented — **PR-E**
- [ ] Boot fails if old AND new alias keys present with different values — **PR-E**
- [ ] No new hardcoded `gostoa.dev` outside `BASE_DOMAIN` derivation in touched code — **all PRs (audit)**
- [ ] `control-plane-api/CLAUDE.md` updated with three new notes — **PR-B (note 1), PR-C (note 2), PR-E (note 3)**
- [ ] Council validation (HEGEMON OS quality gate) — **before Phase 2 kickoff (S7.1)**

### 7.3 — Phase 2 readiness gates (entry to coding)

- [ ] Section 3 Decision Points 1–7 all marked ☑ by Christophe.
- [ ] Pre-flight `pytest` baseline captured (Section 5.1).
- [ ] Pre-flight `argocd app list` audit captured for PR-A (Section 2.1.c).
- [ ] Linear ticket CAB-2199 status updated from Backlog → Todo (per memory `feedback_linear_in_review.md`: Linear "In Review" requires open PR; In Progress when PR-A opens).

---

## Appendix — Cross-references

### A.1 — Ticket → discovery section map

| CAB-2199 sub-scope | Discovery sections | Decisions (Section H) |
|---------------------|-------------------|------------------------|
| Dead k8s cleanup | C.3, C.4, C.5 | Q2 (kill ConfigMap-as-config) |
| `_BASE_DOMAIN` freezing | E.1 | Q1 (Helm vs code SoT), Q6 (multi-env) |
| `OpenSearchSettings` consolidation | E.4, D.7 | (no specific Q) |
| `.env.example` cleanup | A.5, D.6 | Q8 (autogen vs hand-maintained) |
| Pydantic validators (LOG_FORMAT, ENVIRONMENT) | D.1, D.2 | (no specific Q) |
| `STOA_SNAPSHOTS_*` rename | D.4 | Q7 (alias-friendly BC) |
| Multi-env-ready rule | E.1, G.4 | Q6 |
| Documentation | G.3 | (none) |

### A.2 — Files inspected (reproducibility)

```
docs/infra/INFRA-1-DISCOVERY.md (Sections C.3-C.5, D.1-D.2-D.6, E.1, E.4, G, H)
control-plane-api/src/config.py (lines 17, 109-440 sampled)
control-plane-api/src/opensearch/opensearch_integration.py (lines 1-80)
control-plane-api/src/features/error_snapshots/config.py (full)
control-plane-api/.env.example (full)
control-plane-api/CLAUDE.md (full)
control-plane-api/k8s/, portal/k8s/, control-plane-ui/k8s/, stoa-gateway/k8s/, stoa-operator/k8s/ (ls)
control-plane-api/src — grep for derived URL consumers (24 importers, 10 direct sites)
control-plane-api/tests — grep for STOA_SNAPSHOTS_* (10 hits in 2 files)
stoa-gateway/src/config.rs:830-854 — STOA_SNAPSHOT_* (singular, separate scope)
```

### A.3 — Out-of-scope for INFRA-1a (forwarded to 1b/1c/Bug Hunt)

- Chart `MCP_GATEWAY_URL` hardcode (BH-4, P0): → INFRA-1b.
- ExternalSecrets pattern unification (F.2): → INFRA-1b.
- DB plaintext password in chart values (F.4, D.5): → INFRA-1b.
- `STOA_KEYCLOAK_URL` chart hardcode (E.2 / D.10): → INFRA-1b.
- llm_router/federation/api_proxy chart exposure (F.5/F.6/F.7): → INFRA-1b.
- `OPENSEARCH_URL` rename to `DOCS_SEARCH_OPENSEARCH_URL` (D.7): → Bug Hunt or 1b.
- `KEYCLOAK_ADMIN_CLIENT_SECRET` load-time freezing (BH-1): → Phase 2 BH.
- `cross-repo-config-coverage.yml` CI gate (Q5): → INFRA-1c.
- Persona credentials registry (D.9): → INFRA-1c.
- `docs/infra/CONFIG-SOURCES.md`, `SECRETS-VAULT-PATHS.md`, `MULTI-ENV-PLAYBOOK.md`: → INFRA-1c.
- `.env.example` autogen (Q8 long-term): → INFRA-1c (CI lint), then later (autogen).

---

**End of plan.** Phase 1 stops here. Phase 2 (rewrite) starts only after Section 3 arbitrage + Council validation + BH-4 follow-up Linear ticket.

---

## Revision changelog

### v3 — 2026-04-29 (Council Stage 2 adjustments)

3 Council Stage 2 adjustments applied (final score 6.88/10 → target ≥ 8.0 on re-Council):

1. **Secret-value masking in S6 conflict scanner** (Council N3m0 + Pr1nc3ss joint adjustment #1+#2). The `_detect_conflicts_and_emit_deprecation` validator now redacts values for env keys matching `*SECRET*` / `*KEY*` / `*TOKEN*` / `*PASSWORD*` before assembling the raised `ValueError`. The deprecation `logger.warning` line continues to emit KEYS only (no values), with the masking helper kept available as defence-in-depth for any future log changes. Code lives in `docs/infra/INFRA-1a-IMPL-S6.md`. Three new tests added: `test_conflict_redacts_secret_values_in_error_message`, `test_conflict_does_not_redact_non_secret_values`, `test_secret_helper_substring_match`. Test count S6 now 11 (was 8 in v2).
2. **(Joint with #1)** Same masking covers exception + log path.
3. **Plan-length trim** (Council OSS Killer adjustment #3). Implementation code blocks for S2 and S6 extracted to `docs/infra/INFRA-1a-IMPL-S2.md` and `docs/infra/INFRA-1a-IMPL-S6.md`. The master plan §2.2 and §2.6 retain the §a (files), §b (behavioral preservation), §c (summary + companion pointer), §d (test summary), and §e (risks). Master plan target ≤ 30 KB; full code remains versioned in companions.

### v2 — 2026-04-29 (challenger review pass)

10 corrections applied vs v1 (commit `0f1101288`):

1. **S2 wording harmonized**: title, §1.1, §1.2, §1.3 now say "derivation validator" — `@property` is no longer the default plan (still listed as Section 3 #2 alternative).
2. **S2 implementation revised**: `model_validator(mode="after")` + `if not ...` truthiness check replaced with `mode="before")` + `data.setdefault(...)` presence check. Distinguishes absent (derive) from explicit-empty (preserve). New test `test_empty_explicit_url_is_preserved`. Documents the empty-string-preservation as a behavior expansion vs v1.
3. **S6 alias surface extended to dotenv**: per-field `AliasChoices` for resolution + standalone conflict scanner reading BOTH `os.environ` AND `.env` file. Previous v1 design only scanned process env and would have missed the most-likely real-world legacy scenario (developer keeps `STOA_SNAPSHOTS_*` in local `.env`). Two new tests: `test_legacy_alias_from_dotenv_file_is_honored`, `test_conflict_between_new_env_and_old_dotenv_fails`.
4. **Prometheus Counter naming clarified**: Counter constructed as `stoa_deprecated_config_used` (no `_total` in code); `client_python` auto-appends `_total` at exposition. DoD/CLAUDE.md note documents the exposed name `stoa_deprecated_config_used_total`. One-shot guard `_METRIC_EMITTED_KEYS` set + `Lock` added so re-instantiation in tests does not double-count. New test `test_metric_increments_once_per_key_per_process`.
5. **PR sequencing corrected**: PR-A → PR-B → **PR-C → PR-D** → PR-E (was A→B→D→C→E in v1). PR-C before PR-D so OpenSearch consolidation is stable before `.env.example` baseline documents `opensearch_audit`.
6. **PR-D commit messages split**: `LOG_FORMAT: Literal[...]` is `refactor(api)`, not `docs(api)`. PR-D ships TWO commits in ONE PR — `refactor(api)` for validators, `docs(api)` for `.env.example`.
7. **S5 ENVIRONMENT validator narrowed**: surgical `prod → production` mapping, no global `.lower()`. `Staging`, `PRODUCTION`, etc. pass through untouched. Aligns with BH-8 mitigation.
8. **S3 Option A precedence rule**: `_hydrate_opensearch_audit` validator now respects an explicit `Settings(opensearch_audit=...)` and skips flat-field hydration. Added tests for SecretStr unwrap, `model_dump()` exclude=True coverage, explicit-sub-model precedence.
9. **BH-4 escalated to Phase 1 DoD blocker**: a P0 surfaced during planning cannot remain only in a Bug Hunt table. New §7.1 checkbox: "BH-4 follow-up Linear ticket created (owner + priority + linked to INFRA-1b) before Phase 2 starts".
10. **`.env.example` autogen reference rewritten**: removed forward-reference to a non-existent `python -m src.config dump` command. Replaced with "INFRA-1c will add a config dump command and CI diff (no such command exists today; do not copy-paste)".

Plus broader v2 hardening:

- **S1 ArgoCD audit**: command extended to cover `.spec.sources[]` (multi-source apps) — `.spec.source.path` alone misses multi-source apps where ArgoCD ignores the singular field. Plus a broader `git grep` covering Tilt/Makefile/runbooks, not just `.github/workflows/`.
- **Section 0 v2 callout**: added top-of-file "Revision: v2" indicator.

