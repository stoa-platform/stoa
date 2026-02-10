# 🚀 CYCLE 7 — Plan Claude Code (9-15 fév 2026)

**Target: 300 pts** | Vélocité réelle: **~1 pt / 2 min** (5 pts SEO = 8 min) | Mode: FULL SEND

---

## 📊 SCOREBOARD (révisé — audit Claude Code + vélocité réelle)

> **Audit réalité:** 6 tickets avaient 70-100% du code déjà écrit (Cycle 6).
> **Vélocité réelle:** Session 1 (5 pts) = 8 min. Ratio: ~1 pt / 2 min.

| # | Ticket | Pts | PR | Status |
|---|--------|-----|----|--------|
| 1 | CAB-1120 — SEO + Content Compliance | **5** | #203 | ✅ merged |
| 2 | CAB-1121 P1 — Data Model + CRUD APIs | **55** | #204 | ✅ merged |
| 3 | CAB-1097 ADR fix + CAB-1112 Kyverno | **4** | #205 | ✅ merged |
| 4 | CAB-1117 — Sidecar Docker Compose | **8** | #206 | ✅ merged |
| 5 | CAB-1118 — Sidebar Redesign | **8** | #207 + #209 | ✅ merged |
| 6 | CAB-1121 P2 — Keycloak Integration | **20** | #208 | ✅ merged |
| 7 | CAB-1121 P3 — Gateway Propagation | **15** | #211 | ✅ merged + deployed |
| 8 | CAB-1030 + 1068 + 550 + 802 — Docs batch | **22** | #213 | ✅ merged |
| 9 | CAB-1122 — Zero Errors (6 phases) | **—** | #215 | ✅ merged |
| 10 | CAB-362 — Circuit Breaker + Session | **5** | #218 | ✅ merged |
| 11 | CAB-1121 P5 — Portal Consumer UI | **21** | #220 | ✅ merged |
| 12 | CAB-864 P1 — mTLS ADR + Design | **8** | #221 + ADR-039 | ✅ merged |
| 13 | Ship/Show/Ask Git Workflow | **—** | #222 | ✅ merged |
| 14 | AI Factory Modernization + State Files | **—** | — | ✅ Session 21 |
| | | | | |
| | **DONE LUNDI** | **171** | **13 PRs + 1 chore** | ✅ |
| | **DONE DIMANCHE SOIR** | **+41** | **PRs #224-#230** | ✅ |
| | **DONE MARDI** | **+13** | **PRs #233-#235** | ✅ |
| | **DEMO SPRINT D1-D8** | **—** | **PRs #242-#280** | ✅ |
| | | | | |
| 15 | CAB-864 P2 — mTLS Gateway Module | **18** | #224 | ✅ merged |
| 15b | CAB-864 P3 — Bulk Onboarding + Registry | **8** | #230 | ✅ merged |
| 16 | CAB-1121 P4 — Quota Enforcement | **15** | #229 | ✅ merged |
| 17 | CAB-1121 P6 — E2E Tests full flow | **13** | #233 | ✅ merged |
| 18 | CAB-1035 — Persona Alex Test | **2** | — | pending (manuel) |
| 19 | CAB-1066 — Landing + Pricing | **34** | — | pending (stoa-web) |
| | | | | |
| | **REMAINING** | **36** | | |
| | **TOTAL CYCLE 7** | **261** | **225 done** | |

---

## 📅 PLANNING JOUR PAR JOUR

### LUNDI 9 FÉV — ✅ DONE (171 pts, 13 PRs merged)

All sessions completed. PRs #203-#222 merged. Session 21: AI Factory modernization. Highlights:
- CAB-1121 P1-P3+P5: full consumer onboarding pipeline (data→keycloak→gateway→portal UI)
- CAB-1122: zero unjustified errors across all components (6 phases)
- CAB-362: circuit breaker + zombie session reaper
- CAB-864 P1: mTLS design doc + ADR-039 in stoa-docs
- Docs batch: admin guide, AI factory scripts, demo scenarios
- Ship/Show/Ask git workflow for AI Factory
- AI Factory modernization: state files auto-update, rules optimization, context management

---

### REMAINING — Next Sessions

#### CAB-864 P2 — mTLS Gateway Module (18 pts) ✅ PR #224
```
- [x] P2: X.509 header extraction middleware (Rust gateway) — auth/mtls.rs
- [x] P2: RFC 8705 cert-bound token validation (cnf.x5t#S256) — verify_binding()
- [x] P2: Config extensions (MtlsConfig, STOA_MTLS_* env vars)
- [x] P2: Admin endpoints (GET /admin/mtls/config, GET /admin/mtls/stats)
- [x] P2: Fingerprint normalization (hex, hex_colons, base64url) + timing-safe compare
- [x] P2: Trusted proxy CIDR matching, per-route mTLS requirement
- [x] P2: 299 tests pass (32 new), clippy clean
```

#### CAB-864 P3 — Bulk Onboarding + Registry (8 pts) ✅ PR #230
```
- [x] P3: Alembic 020 — 12 certificate columns + 2 fingerprint indexes
- [x] P3: Bulk onboarding (POST /v1/consumers/{tenant_id}/bulk, max 100, CSV)
- [x] P3: Certificate revocation + rotation + Keycloak cnf sync
- [x] P3: 20 new tests, 505 total pass, 54% coverage
```

#### CAB-1121 P4 — Quota Enforcement (15 pts) ✅ PR #229
```
- [x] Rate limiting middleware (per-consumer, per-plan)
- [x] Quota tracking (request counts, bandwidth)
- [x] 429 responses with Retry-After header
- [x] Admin endpoints for quota stats
- [x] 27 new tests, 325 total gateway tests
```

#### CAB-1121 P6 — E2E Tests full flow (13 pts) ✅ PR #233
```
- [x] Full flow: register → subscribe → approve → token exchange → API call
- [x] Contract tests JWT claims schema
- [x] Multi-tenant isolation tests
```

#### CAB-1035 — Persona Alex Test (2 pts, manuel)
```
- [ ] Parcours complet chronométré: signup → discover → first MCP call
- [ ] Frictions documentées en tickets
```

#### CAB-1066 — Landing + Pricing (34 pts, stoa-web)
```
- [ ] Repo stoa-web (Astro)
- [ ] Landing page redesign avec comparison table révisée
- [ ] Pricing page + Stripe integration
- [ ] Content Compliance applied
```

---

## 📊 RÉCAP SCORING

| Status | Points | PRs |
|--------|--------|-----|
| **DONE (Lundi)** | **171** | 13 PRs (#203-#222) + 1 chore |
| **DONE (Dim soir)** | **+41** | PRs #224, #226-#230 + stoa-docs #16 |
| **DONE (Mardi)** | **+13** | PRs #233-#235 |
| **Remaining** | **36** | |
| **Total Cycle 7** | **261** | **225 done (86%)** |

### Remaining breakdown
| Ticket | Pts | Blocker? |
|--------|-----|----------|
| ~~CAB-1121 P6 E2E~~ | ~~13~~ | ✅ PR #233 merged |
| CAB-1035 Persona Alex | 2 | Manual test |
| CAB-1066 Landing | 34 | stoa-web repo, stretch goal → **absorbé dans Premortem L1/B1** |

---

## 🔥 DEMO SPRINT — "ESB is Dead" (10-24 fev 2026)

> Scope: `docs/MVP-SCOPE.md` (approuve 2026-02-10)
> Velocite: 225 pts / 2 jours = AI Factory speed. On ne coupe pas, on livre vite.
> Decision: Rust Gateway = primaire. Pas de retour Python. Observabilite + Federation = IN.

### Semaine 1 (11-16 fev) — Fondations

| # | Action | DoD (binaire) | Jour | Status |
|---|--------|---------------|------|--------|
| S1 | Definir scope demo | `docs/MVP-SCOPE.md` approuve | 10 fev | ✅ |
| D1 | Rust GW basic mode (JWT, proxy, health, rate limit) | Gateway repond 200 + valide JWT + proxy upstream | 11 fev | ✅ PR #242 (compile fix) + PR #244 (docker-compose) |
| D2 | Keycloak federation cross-tenant | Login user realm A → acces ressource realm B | 12 fev | ✅ PR #248 |
| D3 | OpenSearch error snapshots polish | Errors indexees + STOA branding dashboards | 13 fev | ✅ PR #249 |
| D4 | Grafana dashboards (overview, per-tenant, gateway) | 3 dashboards fonctionnels + OIDC Keycloak | 14 fev | ✅ PR #249 |
| D5 | Integration test: full flow admin → consumer → GW → metrics | Script seed-demo + dry-run passe | 15 fev | ✅ PR #249 |

### Semaine 2 (17-23 fev) — Polish + Demo Prep

| # | Action | DoD (binaire) | Jour | Status |
|---|--------|---------------|------|--------|
| D6 | Docker-compose demo final (health checks, nginx routes) | `docker compose up` → tous services healthy | 17 fev | ✅ PR #250 |
| D7 | Demo script 8-act presentation + checklist | Script 8 actes chrono < 20 min | 18 fev | ✅ PR #257 |
| D8 | README public (anglais, badges, quick start) | README.md 185 lines, pret pour repo public | 19 fev | ✅ PR #280 |
| D9 | Bug fixes, dark mode polish, UX consistency | Zero regression, console + portal coherents | 20 fev | ✅ dark mode complete (PRs #234-#247, 8 PRs) |
| D10 | Demo script dry-run #2 (chrono < 15 min) | Dry-run filme, zero blocage | 21 fev | ✅ PR #284 (fixes) — 7/8 acts PASS, Act 7 known (MCP not in Rust GW) |
| D11 | Buffer / derniers ajustements | Zero P0 ouvert | 22-23 fev | pending |

### Demo Day — 24 fev — "ESB is Dead, AI Agents Are Here"

```
Narrative: pas un gateway. Un changement de paradigme.

1. Console: creer tenant "acme" + publier API            (3 min)
2. Portal: s'inscrire, subscribe, obtenir token           (3 min)
3. Rust Gateway: appel API, JWT valide, zero latence      (2 min)
4. Grafana: dashboards live, metriques temps reel         (2 min)
5. OpenSearch: error snapshot, recherche logs STOA        (2 min)
6. Keycloak: federation login cross-tenant                (2 min)
7. MCP Bridge: legacy API → MCP tool pour Claude/GPT      (3 min)
8. AI Factory: "cette plateforme = 225 pts, 22 PRs,      (2 min)
   2 jours, construite par AI Agents — 10 personnes
   font le travail de 300 devs"
```

L'acte 8 est la bombe. L'AI Agent n'est pas une feature, c'est l'ADN.

---

## 🚀 POST-DEMO — Community Launch (24 fev - 10 mars)

> 2 semaines pour polish + public launch. Capitaliser Rust, pas de retour Python.

### PLG Launch

| # | Action | DoD (binaire) | Deadline | Status |
|---|--------|---------------|----------|--------|
| L1 | Repo GitHub public | Visible, README anglais, LICENSE, badges, screenshots | 24 fev | pending |
| L2 | Demo video 3 min | Video publique YouTube/Loom | 24 fev | pending |
| L3 | Tutorial "legacy API → MCP tool" en 5 min | Page docs.gostoa.dev, teste par 3 externes | 7 mars | pending |
| L4 | Post HN "Show HN: STOA" | Post publie, >10 comments | 10 mars | pending |
| L5 | Post Reddit (r/selfhosted, r/devops, r/kubernetes) | 3 posts publies | 10 mars | pending |
| L6 | Listing awesome-mcp-servers | PR merge | 1 mars | pending |
| L7 | Contact Anthropic DevRel | Email envoye + reponse recue | 15 mars | pending |

### Rust Gateway Migration Acceleree

| # | Action | DoD (binaire) | Deadline | Status |
|---|--------|---------------|----------|--------|
| R1 | MCP endpoints dans Rust GW (SSE transport) | MCP tool discovery + proxy en Rust | 7 mars | pending |
| R2 | Kafka metering producer (Rust) | Events publies sur topic, consumer API lit | 10 mars | pending |
| R3 | Python MCP GW = deprecated, Rust = primary | Docker-compose pointe Rust GW pour MCP | 10 mars | pending |

### Business Model + Credibilite

| # | Action | DoD (binaire) | Deadline | Status |
|---|--------|---------------|----------|--------|
| B1 | Pricing page gostoa.dev (Community/Pro/Enterprise) | Page live avec prix | 1 mars | pending |
| B2 | Stripe integration Pro tier ($99-499/mois) | Paiement fonctionnel | 30 avril | pending |
| B3 | Pitch deck 10 slides | PDF envoye a 5 VCs | 1 mars | pending |
| B4 | 3 candidats co-fondateur | 3 conversations >30min | 15 mars | pending |
| B5 | 1 design partner EU | LOI ou MOU signe | 30 avril | pending |
| T1 | Benchmark STOA vs Kong (latency/throughput) | Blog post chiffres reproductibles | 15 mars | pending |
| T2 | 3 blog posts techniques | 3 articles blog.gostoa.dev | 31 mars | pending |
| T3 | CFP KubeCon EU + API Days | 2 CFP soumis | 15 mars | pending |

### Checkpoints

| Checkpoint | Date | Critere binaire |
|-----------|------|----------------|
| **Demo Day** | 24 fev | Plateforme complete demo client |
| **Repo Public** | 24 fev | README + LICENSE + screenshots |
| **HN Launch** | 10 mars | Show HN + quickstart fonctionne |
| **Rust Primary** | 10 mars | Python MCP GW deprecated |
| **100 stars** | 31 mars | github.com/stoa-platform/stoa >= 100 |
| **Design Partner** | 30 avril | 1 LOI signe entreprise EU |
| **First Revenue** | 30 juin | >= $99 MRR |

---

## ✅ DEFINITION OF DONE — Standard Marchemalo (tricouche)

Chaque livrable de chaque session doit passer les 3 couches. Pas de "Done" si une couche manque.

### Couche 1 — Local testé
```
- [ ] Code compile sans erreur
- [ ] Tests unitaires passent (jest/vitest/go test)
- [ ] Lint + format OK (eslint, prettier, golangci-lint)
- [ ] Pas de regression sur tests existants
- [ ] Review code: pas de secret, pas de TODO non-tracké
```

### Couche 2 — Live validé
```
- [ ] Déployé sur env dev/staging (ou docker-compose local pour sidecar)
- [ ] Flow E2E testé manuellement: l'humain voit le résultat attendu
- [ ] Pas d'erreur dans les logs (Loki/stdout)
- [ ] Métriques Prometheus exposées et visibles dans Grafana
- [ ] RBAC vérifié: chaque rôle voit/ne voit pas ce qu'il doit
```

### Couche 3 — Automatisé
```
- [ ] Tests d'intégration (testcontainers ou API tests)
- [ ] CI pipeline vert (GitHub Actions / ArgoCD sync)
- [ ] Si API: OpenAPI spec à jour + tests contract
- [ ] Si UI: screenshot/snapshot tests ou test Cypress/Playwright minimal
- [ ] Si infra: manifests K8s/Helm validés (helm template + kubeval)
```

### Matrice DoD par ticket

| Ticket | Couche 1 (local) | Couche 2 (live) | Couche 3 (auto) |
|--------|-------------------|-----------------|-----------------|
| **CAB-1121** Consumer Onboarding | Unit tests API + DB migrations | Token Exchange flow E2E sur Keycloak dev | Integration tests + contract tests JWT claims |
| **CAB-1118** Sidebar Redesign | Jest components + lint | Console dev: navigation par rôle testée manuellement | Snapshot tests composants sidebar + RBAC matrix |
| **CAB-1117** Sidecar VM | docker-compose up OK | Traffic proxy → upstream, metrics dans Prometheus | CI: docker-compose build + healthcheck + traffic test |
| **CAB-1030** Admin Guide | Build Docusaurus sans erreur | Pages rendues, navigation OK, liens valides | Linkcheck CI (broken links), grep zéro client name |
| **CAB-1068** AI Factory | Scripts exécutables | Premier run-phase.sh réussi | Slack webhook test automatisé |
| **CAB-550** Error Snapshot Demo | Script valide, seed data OK | Flow démo joué 1x complet chrono | Script génération erreurs idempotent |
| **CAB-1112** Kyverno | Policies YAML valides | Pod non-conforme rejeté en live | PolicyReport clean (zéro FAIL légitime) |
| **CAB-362** Circuit Breaker | Unit tests states machine | Simuler pool exhaustion → recovery auto | Integration test: failure injection + recovery |
| **CAB-1120** SEO | Articles build OK | Pages indexables (GSC fetch) | Content Compliance grep (zéro P0 violation) |
| **CAB-802** Demo Script | Markdown valide | Dry run 1x complet < 5min | Checklist pré-démo scriptée |
| **CAB-1035** Persona Alex | N/A (test manuel) | Parcours complet chronométré | Frictions documentées en tickets |
| **CAB-1097** ADR fix | Fichier migré, build OK | Page rendue dans Docusaurus | CI build pass |

---

## ⚡ RÈGLES CLAUDE CODE

1. **Un MEGA par session** — `/clear` entre sessions
2. **Audit avant code** — lire le code existant, conventions, ORM
3. **Council 8/10** — MEGA-tickets seulement si Council GO
4. **Content Compliance** — zéro nom client, zéro prix concurrent, disclaimers
5. **DoD tricouche** — chaque livrable passe local + live + auto AVANT de marquer Done
6. **State files** — memory.md update avant chaque `/clear`
7. **Test "40-year architect"** — un architecte de 40 ans d'expérience comprend le ticket en 30 secondes

---

## 🔗 RÉFÉRENCES

- One-pager: STOA-OnePager-Hybrid-v2 (démo 5 min = flow CAB-1121)
- Content Compliance: document project (P0/P1/P2 rules)
- Linear Cycle 7: 483a7848-51bb-4b7c-a4f6-dbad7a769d08
- Démo target: 24 février 2026
- **Premortem**: `docs/PREMORTEM-STOA-2026.md` — 7 risques fatals, 6 solutions, timeline 90 jours
