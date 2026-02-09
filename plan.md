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
| | | | | |
| 15 | CAB-864 P2-P3 — mTLS Implementation | **26** | — | pending |
| 16 | CAB-1121 P4 — Quota Enforcement | **15** | — | pending |
| 17 | CAB-1121 P6 — E2E Tests full flow | **13** | — | pending |
| 18 | CAB-1035 — Persona Alex Test | **2** | — | pending (manuel) |
| 19 | CAB-1066 — Landing + Pricing | **34** | — | pending (stoa-web) |
| | | | | |
| | **REMAINING** | **90** | | |
| | **TOTAL CYCLE 7** | **261** | | |

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

#### CAB-864 P2-P3 — mTLS Implementation (26 pts)
```
- [ ] P2: X.509 header extraction middleware (Rust gateway)
- [ ] P2: RFC 8705 cert-bound token validation (cnf.x5t#S256)
- [ ] P2: Config extensions (mtls_enabled, trusted_proxies, required_routes)
- [ ] P2: Admin endpoints (/admin/mtls/config, /admin/mtls/stats)
- [ ] P3: Certificate registry model in control-plane-api
- [ ] P3: Bulk onboarding endpoint (POST /certificates/bulk, max 100)
- [ ] P3: Certificate revocation + gateway allowlist sync
```

#### CAB-1121 P4 — Quota Enforcement (15 pts)
```
- [ ] Rate limiting middleware (per-consumer, per-plan)
- [ ] Quota tracking (request counts, bandwidth)
- [ ] 429 responses with Retry-After header
- [ ] Admin endpoints for quota stats
```

#### CAB-1121 P6 — E2E Tests full flow (13 pts)
```
- [ ] Full flow: register → subscribe → approve → token exchange → API call
- [ ] Contract tests JWT claims schema
- [ ] Multi-tenant isolation tests
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
| **Remaining** | **90** | |
| **Total Cycle 7** | **261** | |

### Remaining breakdown
| Ticket | Pts | Blocker? |
|--------|-----|----------|
| CAB-864 P2-P3 mTLS impl | 26 | Design doc ready (PR #221) |
| CAB-1121 P4 Quota | 15 | P1-P3 done, ready to go |
| CAB-1121 P6 E2E | 13 | Needs P4 first |
| CAB-1035 Persona Alex | 2 | Manual test |
| CAB-1066 Landing | 34 | stoa-web repo, stretch goal |

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
