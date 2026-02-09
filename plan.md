# 🚀 CYCLE 7 — Plan Claude Code (9-15 fév 2026)

**Target: 300 pts** | Vélocité réelle: **~1 pt / 2 min** (5 pts SEO = 8 min) | Mode: FULL SEND

---

## 📊 SCOREBOARD (révisé — audit Claude Code + vélocité réelle)

> **Audit réalité:** 6 tickets avaient 70-100% du code déjà écrit (Cycle 6).
> **Vélocité réelle:** Session 1 (5 pts) = 8 min. Ratio: ~1 pt / 2 min.

| # | Ticket | Pts | Durée réelle | Jour prévu |
|---|--------|-----|-------------|------------|
| 1 | CAB-1121 — Consumer Onboarding P1 (Data Model) | **55** | ✅ PR #204 merged | ✅ Lun |
| 1b | CAB-1121 — Consumer Onboarding P2 (Keycloak) | **20** | ✅ PR #208 merged | ✅ Lun |
| 1c | CAB-1121 — Consumer Onboarding P3 (Gateway) | **15** | ✅ Code done, PR pending | ✅ Lun |
| 2 | CAB-1118 — Sidebar Redesign | **8** | ✅ PR #207 + #209 merged | ✅ Lun |
| 3 | CAB-1117 — Sidecar Docker Compose | **8** | ✅ PR #206 merged | ✅ Lun |
| 4 | CAB-1030 — Admin Guide + Onboarding | **13** | ~25 min | Mar |
| 5 | CAB-1068 — AI Factory Setup | **3** | ~6 min | Mar |
| 6 | CAB-1120 — SEO + Compliance | **5** | ✅ 8 min (done) | ✅ Lun |
| 7 | CAB-550 — Error Snapshot Demo | **3** | ~6 min | Mar |
| 8 | CAB-802 — Demo Dry Run Script | **3** | ~6 min | Mar |
| 9 | CAB-1112 — Kyverno Enforce | **2** | ✅ PR #205 merged | ✅ Lun |
| 10 | CAB-1035 — Persona Alex Test | **2** | ~15 min (manuel) | Mar |
| 11 | CAB-1097 — ADR fix | **2** | ✅ PR #205 merged | ✅ Lun |
| 12 | CAB-362 — Circuit Breaker + Session | **5** | ~10 min | Mar |
| 13 | Content Compliance apply | **5** | ✅ PR #203 merged | ✅ Lun |
| | | | | |
| | **SUBTOTAL BASE** | **94** | **~3h** | **Lun-Mar** |
| | **DONE Lun (P1+P2+P3+Sidebar+Sidecar+Kyverno+ADR+SEO+Compliance)** | **120** | | ✅ |
| | | | | |
| 14 | CAB-864 — mTLS Epic | **34** | ~70 min | Mar-Mer |
| 15 | CAB-1121 P4 — Quota Enforcement | **15** | ~30 min | Mar |
| 16 | CAB-1121 P5 — Portal Consumer UI | **21** | ~40 min | Mer |
| 17 | CAB-1121 P6 — E2E Tests full flow | **13** | ~25 min | Mer |
| 18 | CAB-1066 — Landing + Pricing | **34** | ~70 min | Mer-Jeu |
| | | | | |
| | **TOTAL PLANIFIÉ** | **196** | **~6h** | **Lun→Mer** |
| | **AVEC mTLS + P4-P6** | **279** | **~9h** | **Lun→Mer** |
| | **AVEC Landing** | **313** | **~11h** | **Lun→Jeu** |

---

## 📅 PLANNING JOUR PAR JOUR

### LUNDI 9 FÉV — "Sprint Day" (~130 pts, ~4h30)

#### Session 1: CAB-1120 SEO + Compliance (5 pts) — ✅ DONE (8 min)

#### Session 1b: Content Compliance Agent (5 pts) — ✅ DONE (PR #203 merged)

#### Session 1c: CAB-1121 P1 — Data Model + CRUD APIs (55 pts) — ✅ DONE (PR #204 merged)
- Consumer model + Plan model + Alembic migration 018
- 14 REST endpoints (8 consumer + 6 plan) with tenant isolation
- 23 tests, full suite 452 passed, coverage 54%
- Full CI/CD green through deploy + smoke test

#### Session 2: CAB-1121 P2 — Keycloak + OAuth2 (20 pts) — ✅ DONE (PR #208 merged)
- Consumer registration → auto-create OAuth2 client in Keycloak
- client_id = `{tenant}-{consumer_external_id}`, client_secret auto-generated
- Service account enabled for client_credentials grant
- Failure mode: 503 + logged warning, non-blocking
- 10 tests added, 485 total pass, coverage 54%

#### Session 3: CAB-1121 P3 — Gateway Propagation (15 pts) — ✅ DONE (code ready, PR pending)
- Enriched app_spec with consumer + plan context on provision
- STOA adapter: provision_application → sync_api + upsert_policy
- webMethods adapter: idempotent provision (check existing by name)
- Rate-limit policy push on approval, cleanup on deprovision
- 22 new tests (485 total pass, coverage 54.22%)

#### Session 4: CAB-1118 Sidebar finitions (8 pts) — ✅ DONE (PR #207 + #209 merged)
- Collapsible sidebar sections, tenant dropdown, skeleton pages
- Function coverage boost above 35%

#### Session 5: CAB-1117 Sidecar Docker Compose (8 pts) — ✅ DONE (PR #206 merged)
- docker-compose.sidecar.yml demo scenario

#### Session 6: CAB-1112 Kyverno (2 pts) + CAB-1097 ADR fix (2 pts) — ✅ DONE (PR #205 merged)
- Kyverno: 5 ClusterPolicies Audit → Enforce
- ADR-027→035, ADR-028→036, ADR-033→037 renumbered

---

### MARDI 10 FÉV — "Docs + Polish Day" (~80 pts, ~3h)

#### Session 7: CAB-1030 Admin Guide (13 pts) — ~25 min
```
- [ ] /docs/admin/ 12 pages (overview→upgrade)
- [ ] OpenShift delta (SCC, Routes, registry, non-root)
- [ ] Onboarding Kit Cédric (privé)
- [ ] Content Compliance scan: zéro client name
```

#### Session 8: CAB-1068 AI Factory (3 pts) — ~6 min
```
- [ ] Templates: MEGA-TICKET.md, PHASE-PLAN.md
- [ ] Scripts: run-phase.sh, slack-notify.sh
```

#### Session 9: CAB-550 Error Snapshot Demo (3 pts) — ~6 min
```
- [ ] Script démo 2 min + seed data generator
```

#### Session 10: CAB-802 Demo Dry Run Script (3 pts) — ~6 min
```
- [ ] Script markdown avec timing par étape (aligné one-pager flow)
- [ ] Checklist pré-démo + Plan B
```

#### Session 11: CAB-362 Circuit Breaker (5 pts) — ~10 min
```
- [ ] Session management: zombie detection + reaper
- [ ] Per-upstream config (actuellement générique)
```

#### Session 12: CAB-1035 Persona Alex (2 pts) — ~15 min
```
- [ ] Parcours complet chronométré: signup → discover → first MCP call
- [ ] Frictions documentées en tickets
```

#### Session 13: CAB-864 mTLS P1 — Design + ADR (8 pts) — ~15 min
```
- [ ] ADR: F5 mTLS termination → STOA → webMethods flow
- [ ] RFC 8705 cert-bound tokens spec
- [ ] Architecture diagram
```

---

### MERCREDI 11 FÉV — "Stretch Day" (~90 pts, ~3h)

#### Session 14: CAB-864 mTLS P2-P3 — Implémentation (26 pts) — ~50 min
```
- [ ] F5 X.509 header extraction
- [ ] Certificate-bound tokens implementation
- [ ] 100-client bulk onboarding flow
```

#### Session 15: CAB-1121 P5 — Portal Consumer UI (21 pts) — ~40 min
```
- [ ] Portal UI: consumer registration form
- [ ] Subscription workflow UI: browse catalogue → select plan → request access
- [ ] Owner approval UI: notification + approve/reject
- [ ] Credentials display (one-time)
```

#### Session 16: CAB-1121 P6 — E2E Tests (13 pts) — ~25 min
```
- [ ] Full flow test: register → subscribe → approve → token exchange → API call
- [ ] Contract tests JWT claims schema
- [ ] Multi-tenant isolation tests
```

---

### JEUDI 12 FÉV — "Bonus Day" (si avance, ~34 pts)

#### Session 17: CAB-1066 Landing + Pricing (34 pts) — ~70 min
```
- [ ] Repo stoa-web (Astro)
- [ ] Landing page redesign avec comparison table révisée
- [ ] Pricing page + Stripe integration
- [ ] Content Compliance applied
```

---

## 📊 RÉCAP SCORING (révisé — vélocité 1pt/2min)

| Jour | Tickets | Points | Durée |
|------|---------|--------|-------|
| **Lundi** ✅ | S1 SEO ✅ + S1b Compliance ✅ + S1c P1 ✅ + S2 Keycloak ✅ + S3 Gateway ✅ + S4 Sidebar ✅ + S5 Sidecar ✅ + S6 Kyverno+ADR ✅ | **120** | done |
| **Mardi** | S7 Admin Guide (13) + S8 Factory (3) + S9 Demo (3) + S10 Script (3) + S11 CB (5) + S12 Alex (2) + S13 mTLS design (8) + P4 Quota (15) | **52** | ~2h |
| **Mercredi** | S14 mTLS impl (26) + S15 Portal UI (21) + S16 E2E (13) | **60** | ~2h |
| **Jeudi** | S17 Landing (34) | **34** | ~1h10 |
| | | | |
| **DONE (Lundi)** | | **120** | |
| **+ Mardi** | | **172** | |
| **+ Mercredi** | | **232** | |
| **+ Jeudi** | | **266** | |

### Blockers identifiés
1. **Keycloak Token Exchange SPI** — si config realm non-triviale, Session 2 peut glisser
2. **Vault root token** — pas bloquant Cycle 7 (workaround K8s secrets)
3. **CAB-1066** — context switch repo stoa-web, à ne prendre que si avance réelle

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
