# Claude Squad Strategy — Cycle 7 Remaining

> Generated 2026-02-09. S1-S6 DONE. S3 (P3 Gateway) IN PROGRESS via CLI.

## Status

| Session | Ticket | Pts | Status |
|---------|--------|-----|--------|
| S1c | CAB-1121 P1 | 55 | DONE (PR #204) |
| S2 | CAB-1121 P2 | 20 | DONE (PR #208) |
| S3 | CAB-1121 P3 | 15 | IN PROGRESS (CLI) |
| S4 | CAB-1118 Sidebar | 8 | DONE (PR #207 + #209) |
| S5 | CAB-1117 Sidecar | 8 | DONE (PR #206) |
| S6 | CAB-1112 + CAB-1097 | 4 | DONE (PR #205) |

**Remaining: 10 sessions, ~146 pts**

---

## Wave 1 — Parallel (no dependencies)

Launch these 4 Squad instances simultaneously. Zero file overlap.

### SQUAD A: CAB-362 Circuit Breaker (5 pts)

**Branch:** `feat/cab-362-circuit-breaker-session`
**Scope:** `stoa-gateway/` (Rust only)
**Estimated:** ~10 min

```
CAB-362 — Circuit Breaker + Session Management (stoa-gateway Rust).

CONTEXTE:
- stoa-gateway/src/resilience/circuit_breaker.rs existe deja (335 lignes, Hystrix-style, 13 tests)
- stoa-gateway/src/mcp/session.rs existe (SessionManager avec TTL)
- stoa-gateway/src/governance/zombie.rs existe (ZombieDetector, ADR-012, 648 lignes, 10 tests)

TACHES:
1. Per-upstream circuit breaker config:
   - Actuellement le circuit breaker est generique (un seul config pour tous les upstreams)
   - Ajouter CircuitBreakerConfig par upstream dans config.rs
   - Map<upstream_id, CircuitBreakerConfig> dans AppState
   - Defaults sensibles: failure_threshold=5, reset_timeout=30s, half_open_max=3

2. Session zombie detection wiring:
   - Wire ZombieDetector dans le lifecycle des sessions (SessionManager)
   - Reaper task: tokio::spawn background qui run toutes les 60s
   - Sur detection zombie: log warn + close session + increment metric
   - Admin endpoint GET /admin/zombies pour stats

3. Config fields dans config.rs:
   - circuit_breaker_per_upstream: bool (default false)
   - zombie_reaper_interval_secs: u64 (default 60)
   - zombie_session_ttl_secs: u64 (default 300)

4. Tests:
   - Test per-upstream CB: upstream A tripped, upstream B still closed
   - Test zombie reaper: expired session detected + cleaned
   - Test admin endpoint returns zombie stats

REGLES:
- Lis le code existant AVANT de coder (circuit_breaker.rs, zombie.rs, session.rs, config.rs)
- cargo fmt + clippy zero warnings (RUSTFLAGS=-Dwarnings)
- cargo test --all-features doit passer
- Pas de todo!() ni unimplemented!() (SAST bloque)
- Branch: feat/cab-362-circuit-breaker-session
- Commit: feat(gateway): per-upstream circuit breaker + zombie session reaper (CAB-362)
```

---

### SQUAD B: CAB-1121 P5 Portal Consumer UI (21 pts)

**Branch:** `feat/cab-1121-portal-consumer-ui`
**Scope:** `portal/` (React/TS only)
**Estimated:** ~40 min
**Dependency:** P2 API endpoints DONE (PR #208)

```
CAB-1121 Phase 5 — Portal Consumer UI.

CONTEXTE:
- Phase 1 (data model + 14 REST endpoints) = DONE (PR #204)
- Phase 2 (Keycloak OAuth2 integration) = DONE (PR #208)
- Phase 3 (Gateway Propagation) = EN COURS
- Les endpoints API existent: GET/POST /v1/tenants/{slug}/consumers, GET/POST /v1/tenants/{slug}/plans, etc.
- Portal structure: portal/src/pages/ (14 page dirs existants)
- Portal utilise: React 18, TypeScript, Vite, vitest, React Testing Library
- Style: Tailwind CSS, composants fonctionnels + hooks
- Auth: Keycloak-js

TACHES:
1. API client layer:
   - portal/src/api/consumers.ts: CRUD consumers (GET list, GET detail, POST create, PATCH update)
   - portal/src/api/plans.ts: GET plans list, GET plan detail
   - Utiliser le pattern existant (voir portal/src/api/ pour conventions)

2. Pages Consumer:
   - portal/src/pages/consumers/MyConsumers.tsx: liste des consumers du tenant
   - portal/src/pages/consumers/ConsumerRegistration.tsx: formulaire inscription
   - portal/src/pages/consumers/ConsumerDetail.tsx: detail + subscriptions

3. Composants:
   - portal/src/components/consumers/ConsumerForm.tsx: form (name, external_id, contact_email, description)
   - portal/src/components/consumers/PlanSelector.tsx: browse plans, select tier
   - portal/src/components/consumers/SubscriptionRequestForm.tsx: request access avec plan selectionne
   - portal/src/components/consumers/CredentialsDisplay.tsx: affichage one-time client_id/secret

4. Integration navigation:
   - Ajouter "Consumers" dans portal/src/pages/workspace/WorkspacePage.tsx (nouveau tab)
   - Ajouter routes dans le router (App.tsx ou equivalent)
   - Lien dans la sidebar si applicable

5. Tests vitest:
   - Test render de chaque page/composant
   - Test form validation (required fields, email format)
   - Test API mock calls
   - Coverage: maintenir > 20 warnings max ESLint, prettier clean

REGLES:
- Lis portal/src/api/ et portal/src/pages/ AVANT de coder pour suivre les conventions
- npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit
- npm run test -- --run
- Branch: feat/cab-1121-portal-consumer-ui
- Commit: feat(portal): consumer registration + subscription workflow UI (CAB-1121 P5)
```

---

### SQUAD C: Docs + Scripts batch (22 pts)

**Branch:** `docs/cab-1030-admin-guide`
**Scope:** `docs/` + `scripts/` (zero code overlap)
**Estimated:** ~45 min

```
Batch de 4 tickets docs/scripts — CAB-1030 + CAB-1068 + CAB-550 + CAB-802.

CONTEXTE:
- docs/demo/ existe deja (DEMO-SCRIPT.md, DEMO-CHECKLIST.md, DRY-RUN-1.md)
- .stoa-ai/ peut exister (AI Factory templates)
- Content compliance: .claude/rules/content-compliance.md (zero nom client, zero prix concurrent)
- STOA = "The European Agent Gateway", API Management AI-Native, Apache 2.0
- Docusaurus docs = stoa-docs repo (separe). Ici on fait les docs operationnelles du monorepo.

TICKET 1 — CAB-1030 Admin Guide (13 pts):
Creer docs/admin/ avec 10 pages operationnelles (pas dans stoa-docs, c'est la partie ops interne):
1. docs/admin/README.md — overview admin STOA (architecture, composants, prerequis)
2. docs/admin/installation.md — install EKS/Helm step-by-step
3. docs/admin/configuration.md — env vars, secrets, BASE_DOMAIN
4. docs/admin/rbac.md — roles Keycloak (cpi-admin, tenant-admin, devops, viewer)
5. docs/admin/secrets-rotation.md — procedure rotation (Vault + ESO)
6. docs/admin/monitoring.md — Prometheus + Grafana + OpenSearch stack
7. docs/admin/backup-restore.md — PostgreSQL, Keycloak realm export, MinIO
8. docs/admin/troubleshooting.md — common issues + resolution
9. docs/admin/upgrade.md — upgrade procedure (Helm + DB migrations)
10. docs/admin/openshift-delta.md — SCC, Routes vs Ingress, registry, non-root

TICKET 2 — CAB-1068 AI Factory (3 pts):
- Verifier/creer docs/templates/MEGA-TICKET.md (template mega-ticket avec scoring)
- Verifier/creer docs/templates/PHASE-PLAN.md (template plan phase)
- Creer scripts/run-phase.sh (lance une phase Claude Code, args: ticket-id, phase-number)
- Creer scripts/slack-notify.sh (envoie notification Slack webhook, args: message, channel)
- Chmod +x sur les scripts

TICKET 3 — CAB-550 Error Snapshot Demo (3 pts):
- docs/demo/error-snapshot-demo.md: scenario demo 2 min montrant error correlation
  - Flow: API call fails → trace correlation across services → OpenSearch snapshot
  - Talking points pour le presentateur
- scripts/seed-error-snapshot.py: script Python qui seed des erreurs de demo
  - Appels API qui generent des erreurs controlees (400, 500, timeout)
  - Ecriture directe dans OpenSearch si dispo, sinon stdout JSON

TICKET 4 — CAB-802 Demo Dry Run Script (3 pts):
- scripts/demo-dry-run.sh: script bash qui teste tous les endpoints de la demo
  - Pre-flight checks (curl services health)
  - Timing par segment (API, Portal, Gateway, MCP)
  - Output markdown PASS/FAIL
- docs/demo/DEMO-PLAN-B.md: plan B si blockers pendant demo
  - Scenarios de fallback par composant
  - Contacts urgence

REGLES:
- Lis docs/demo/ existants AVANT de creer pour ne pas dupliquer
- ZERO nom de client dans le contenu (compliance P0)
- ZERO prix de concurrent (compliance P0)
- Si mention de competitor: source + date "last verified" obligatoire
- Scripts: shebang #!/usr/bin/env bash, set -euo pipefail
- Commits conventionnels separes par ticket:
  1. docs(admin): add operational admin guide 10 pages (CAB-1030)
  2. chore(ai-factory): add templates and automation scripts (CAB-1068)
  3. docs(demo): error snapshot demo script + seed data (CAB-550)
  4. docs(demo): dry run automation script + plan B (CAB-802)
- Branch: docs/cab-1030-admin-guide (un seul branch pour les 4)
```

---

### SQUAD D: CAB-864 mTLS P1 — ADR + Design (8 pts)

**Branch:** `feat/cab-864-mtls-design`
**Scope:** `docs/` (ADR only, pas de code)
**Estimated:** ~15 min

```
CAB-864 Phase 1 — mTLS Architecture Design + ADR.

CONTEXTE:
- STOA Gateway (Rust, axum) recoit du trafic derriere F5 BigIP (TLS termination)
- F5 fait mTLS termination et forward les headers X.509 (X-SSL-Client-Cert, X-SSL-Client-S-DN, etc.)
- Gateway doit extraire les infos certificat et implementer RFC 8705 (cert-bound tokens)
- Keycloak gere les tokens OAuth2 (Phase 2 consumer onboarding DONE)
- stoa-gateway/src/auth/ a deja: jwt.rs, oidc.rs, api_key.rs, rbac.rs, middleware.rs, claims.rs
- ADR numbering: stoa-docs owns numbers (001-038). Ici on fait un draft ADR dans stoa repo.

TACHES:
1. ADR draft — docs/architecture/adr-draft-mtls-cert-bound-tokens.md:
   - Title: "F5 mTLS Termination + RFC 8705 Certificate-Bound Tokens"
   - Context: F5 terminates TLS, forwards X.509 headers to STOA Gateway
   - Decision: Extract cert metadata from headers, bind to OAuth2 tokens via `cnf` claim
   - Flow diagram (ASCII):
     Client --mTLS--> F5 BigIP --X.509 headers--> STOA Gateway --verify cnf--> Backend
   - Headers expected: X-SSL-Client-Cert, X-SSL-Client-S-DN, X-SSL-Client-Serial, X-SSL-Client-Fingerprint
   - Token binding: SHA-256 thumbprint of client cert stored in JWT `cnf.x5t#S256`
   - Validation: Gateway extracts cert thumbprint from header, compares with `cnf` in JWT
   - Consequences: requires Keycloak protocol mapper for `cnf` claim

2. Architecture diagram — docs/architecture/mtls-flow.md:
   - Detailed flow: 6 steps (client cert → F5 → headers → gateway → token verify → backend)
   - Bulk onboarding flow: 100 clients (CSV → API → Keycloak clients + certs)
   - Failure modes: missing header, thumbprint mismatch, expired cert

3. RFC 8705 spec summary — dans l'ADR:
   - Section "RFC 8705 Compliance"
   - `cnf` claim format: {"x5t#S256": "<base64url-encoded-sha256-thumbprint>"}
   - Token endpoint: must include client cert in token request
   - Resource server: must verify binding

REGLES:
- PAS de code dans cette phase (design only)
- ADR format standard: Status, Context, Decision, Consequences
- Draft ADR sera renumerote quand migre vers stoa-docs
- Branch: feat/cab-864-mtls-design
- Commit: docs(architecture): mTLS + RFC 8705 cert-bound tokens ADR (CAB-864 P1)
```

---

## Wave 2 — After Wave 1 merges

### SQUAD E: CAB-864 mTLS P2-P3 Implementation (26 pts)

**Branch:** `feat/cab-864-mtls-impl`
**Scope:** `stoa-gateway/` (Rust)
**Depends on:** SQUAD A merged (both touch `config.rs`), SQUAD D merged (design)
**Estimated:** ~50 min

```
CAB-864 Phases 2-3 — mTLS Implementation (stoa-gateway Rust).

PREREQUIS: Phase 1 ADR merged. CAB-362 circuit breaker merged (config.rs changes).

CONTEXTE:
- ADR mTLS decide: F5 forward X.509 headers, gateway extract + verify cnf claim
- stoa-gateway/src/auth/ existant: jwt.rs, oidc.rs, api_key.rs, rbac.rs, middleware.rs, claims.rs
- RFC 8705: cnf claim = {"x5t#S256": "<base64url-sha256-thumbprint>"}
- Config existante dans config.rs (lire la version actuelle apres merge CAB-362)

TACHES:
1. Module mTLS — stoa-gateway/src/auth/mtls.rs (NEW):
   - Struct MtlsExtractor: extract cert metadata from request headers
   - Headers: X-SSL-Client-Cert, X-SSL-Client-S-DN, X-SSL-Client-Serial, X-SSL-Client-Fingerprint
   - Fn extract_cert_thumbprint(headers: &HeaderMap) -> Result<String>
   - Fn verify_cert_binding(thumbprint: &str, cnf_claim: &CnfClaim) -> bool
   - Base64url-encode SHA-256 thumbprint

2. Claims extension — stoa-gateway/src/auth/claims.rs:
   - Ajouter champ optionnel `cnf: Option<CnfClaim>` dans Claims struct
   - Struct CnfClaim { #[serde(rename = "x5t#S256")] x5t_s256: String }

3. Middleware integration — stoa-gateway/src/auth/middleware.rs:
   - Si mtls_enabled dans config: extraire thumbprint AVANT JWT validation
   - Apres JWT validation: si cnf claim present, verifier binding
   - Mismatch → 403 Forbidden avec message "certificate binding mismatch"
   - Header absent + mtls_required → 401

4. Config — stoa-gateway/src/config.rs:
   - mtls_enabled: bool (default false)
   - mtls_header_name: String (default "X-SSL-Client-Cert")
   - mtls_require_binding: bool (default false, true = reject tokens without cnf)

5. Bulk onboarding endpoint — stoa-gateway/src/handlers/admin.rs:
   - POST /admin/consumers/bulk: accept CSV (name, cert_cn, email) → batch create
   - Limit: 100 consumers per request
   - Response: JSON array of {consumer_id, status, error?}

6. Tests:
   - Test extract thumbprint from headers (valid, missing, malformed)
   - Test cnf binding verification (match, mismatch)
   - Test middleware: mtls_enabled=true + valid cert → pass
   - Test middleware: mtls_enabled=true + mismatch → 403
   - Test middleware: mtls_enabled=false → skip mTLS check
   - Test bulk onboarding: 5 consumers CSV → 5 created

REGLES:
- cargo fmt + clippy zero warnings
- cargo test --all-features
- Pas de todo!() ni unimplemented!()
- Pas de unwrap() dans le code production (ok dans tests)
- Branch: feat/cab-864-mtls-impl
- Commit: feat(gateway): mTLS X.509 extraction + RFC 8705 cert-bound tokens (CAB-864 P2-P3)
```

---

### SQUAD F: CAB-1121 P6 E2E Tests (13 pts)

**Branch:** `feat/cab-1121-e2e-consumer`
**Scope:** `e2e/` (Playwright BDD only)
**Depends on:** SQUAD B merged (Portal UI), P3 done (Gateway)
**Estimated:** ~25 min

```
CAB-1121 Phase 6 — E2E Tests Consumer Flow.

PREREQUIS: Portal Consumer UI merged (P5). Gateway Propagation done (P3).

CONTEXTE:
- e2e/ utilise Playwright + playwright-bdd (Gherkin .feature files)
- e2e/features/portal-consumer-flow.feature EXISTE deja (scenarios de base)
- e2e/steps/consumer-flow.steps.ts EXISTE deja (step definitions de base)
- Auth: persona storage states dans fixtures/.auth/
- Markers: @smoke, @critical, @portal, @consumer
- Config: playwright.config.ts avec projects auth-setup, portal-chromium, console-chromium

TACHES:
1. Expand e2e/features/portal-consumer-flow.feature:
   - Scenario: Full consumer registration flow
     Given I am logged in as tenant-admin
     When I navigate to Consumers page
     And I click "Register Consumer"
     And I fill consumer form (name, external_id, email)
     Then consumer is created with status "active"

   - Scenario: Subscription request + approval flow
     Given a consumer exists
     When consumer requests subscription to plan "starter"
     Then subscription status is "pending_approval"
     When tenant-admin approves the subscription
     Then subscription status is "active"
     And credentials are displayed once

   - Scenario: Multi-tenant isolation
     Given consumer in tenant-A
     When I switch to tenant-B
     Then I cannot see tenant-A consumers

2. NEW e2e/features/consumer-jwt-contract.feature:
   - Scenario: JWT claims contract validation
     Given consumer with approved subscription
     When token exchange is performed
     Then JWT contains claims: tenant_id, consumer_id, plan, scopes, rate_limit

3. Expand e2e/steps/consumer-flow.steps.ts:
   - Steps pour navigation Consumer pages
   - Steps pour form fill + submit
   - Steps pour approval workflow
   - Steps pour credentials display verification

4. NEW e2e/steps/token-exchange.steps.ts:
   - Step: perform token exchange via API call
   - Step: decode JWT and validate claims
   - Step: verify claim values match consumer/plan data

REGLES:
- Lis e2e/features/ et e2e/steps/ existants AVANT de coder
- Pas de step definitions dupliquees (bug passe, voir PRs #191, #196)
- Tag @wip sur scenarios qui necessitent infra running
- npx bddgen pour regenerer apres ajout de features
- Branch: feat/cab-1121-e2e-consumer
- Commit: test(e2e): full consumer onboarding flow + JWT contract tests (CAB-1121 P6)
```

---

## Wave 3 — Bonus (separate repo)

### SQUAD G: CAB-1066 Landing + Pricing (34 pts)

**Repo:** `stoa-web` (Astro) — PAS le monorepo stoa
**Branch:** `feat/cab-1066-landing-pricing`
**Estimated:** ~70 min

```
CAB-1066 — Landing Page Redesign + Pricing (stoa-web repo, Astro).

CONTEXTE:
- Repo: stoa-platform/stoa-web (Astro framework)
- STOA = "The European Agent Gateway"
- Kill feature: UAC (Universal API Contract) — "Define Once, Expose Everywhere"
- Open source Apache 2.0
- Content compliance: .claude/rules/content-compliance.md (CRITIQUE)

TACHES:
1. Landing page redesign (src/pages/index.astro):
   - Hero: "The European Agent Gateway" + tagline UAC
   - 3 value props: Legacy-to-MCP Bridge, UAC, Hybrid Deployment
   - Comparison table (vs Kong, Apigee, MuleSoft) avec disclaimers OBLIGATOIRES
   - CTA: "Get Started" → docs.gostoa.dev

2. Pricing page (src/pages/pricing.astro):
   - 3 tiers: Community (free, OSS), Professional, Enterprise
   - Community: unlimited APIs, community support
   - Professional: SLA, priority support, SSO
   - Enterprise: mTLS, custom deployment, dedicated support
   - PAS de prix specifiques concurrents (P0 compliance)
   - Stripe integration: checkout links (env var STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_ENT)

3. Comparison table component:
   - Features: MCP Support, Hybrid Deploy, Open Source, UAC, mTLS
   - Format: "As of [YYYY-MM], [product] [does/does not] offer [feature]"
   - Source links obligatoires
   - Disclaimer footer template (voir content-compliance.md)

4. Content Compliance (OBLIGATOIRE):
   - ZERO prix specifiques concurrents
   - ZERO "better than", "superior to" — utiliser "alternative to", "compared to"
   - ZERO "legacy", "outdated" — utiliser formulations neutres
   - Disclaimer sur chaque page comparative
   - Trademark attributions

REGLES:
- cd stoa-web (PAS stoa monorepo)
- Respecter content-compliance.md a la lettre
- Branch: feat/cab-1066-landing-pricing
- Commits:
  1. feat(web): landing page redesign with UAC hero (CAB-1066)
  2. feat(web): pricing page with 3 tiers (CAB-1066)
  3. feat(web): comparison table with compliance disclaimers (CAB-1066)
```

---

## Execution Timeline

```
TIME    SQUAD A          SQUAD B           SQUAD C           SQUAD D
        CB+Session       Portal UI         Docs batch        mTLS ADR
        (Rust 5pts)      (React 21pts)     (Docs 22pts)      (Docs 8pts)
─────── ──────────────── ───────────────── ───────────────── ─────────────
0:00    START            START             START             START
0:10    DONE→PR          |                 |                 DONE→PR
0:15    |                |                 |                 |
0:30    |                |                 |                 |
0:40    |                DONE→PR           |                 |
0:45    |                |                 DONE→PR           |
─────── ──────────────── ───────────────── ───────────────── ─────────────
        MERGE ALL WAVE 1 PRs
─────── ──────────────── ───────────────── ───────────────── ─────────────
        SQUAD E                  SQUAD F
        mTLS Impl (Rust 26pts)   E2E Tests (13pts)
─────── ──────────────────────── ─────────────────────────────
0:50    START                    START
1:15    |                        DONE→PR
1:40    DONE→PR                  |
─────── ──────────────────────── ─────────────────────────────
        MERGE ALL WAVE 2 PRs
─────── ──────────────────────── ─────────────────────────────
        SQUAD G (optional, separate repo)
        Landing+Pricing (34pts)
─────── ─────────────────────────
2:00    START
3:10    DONE→PR
```

## Quick Reference

| Squad | Branch | Scope | Conflict zone | Wave |
|-------|--------|-------|---------------|------|
| A | feat/cab-362-circuit-breaker-session | stoa-gateway/ | config.rs | 1 |
| B | feat/cab-1121-portal-consumer-ui | portal/ | none | 1 |
| C | docs/cab-1030-admin-guide | docs/ + scripts/ | none | 1 |
| D | feat/cab-864-mtls-design | docs/architecture/ | none | 1 |
| E | feat/cab-864-mtls-impl | stoa-gateway/ | config.rs (after A) | 2 |
| F | feat/cab-1121-e2e-consumer | e2e/ | none | 2 |
| G | feat/cab-1066-landing-pricing | stoa-web repo | none | 3 |

## Merge Order (strict)

1. Wave 1: A + B + C + D (parallel merge, no conflicts)
2. Wave 2: E (after A merged) + F (after B merged)
3. Wave 3: G (independent repo)

## Total Points

| Wave | Squads | Points |
|------|--------|--------|
| Wave 1 | A + B + C + D | 56 pts |
| Wave 2 | E + F | 39 pts |
| Wave 3 | G | 34 pts |
| **TOTAL** | **7 Squads** | **129 pts** |
| + P3 en cours (CLI) | | **+15 pts = 144 pts** |
