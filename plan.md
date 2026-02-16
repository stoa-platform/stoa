# Sprint Plan — STOA Platform

> Auto-synced with Linear via `/sync-plan`. Source of truth: Linear cycles.
> Last sync: 2026-02-16

## Cycle 7 (Feb 9–15) — CLOSED

**Scope**: 505 pts | **Done**: 505 pts (100%) | **Velocity**: 44 issues closed
**Theme**: Code critique + Polish + AI Factory v2 + Demo Prep + Community Infra

### Done (44 issues)

- [x] CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — PR #423 + E2E PR #450
- [x] CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts) — stoactl PR #6, stoa PR #436
- [x] CAB-864: mTLS + OAuth2 Certificate Binding (34 pts) — PRs #425-#429, #453
- [x] CAB-1031: Plan d'Action SI Post-Demo (21 pts) — stoa-strategy
- [x] CAB-550: Error Snapshot Scenario (3 pts) — PR #448
- [x] CAB-872: mTLS Integration E2E (8 pts) — PR #453
- [x] CAB-1066: Landing + Pricing refonte (21 pts) — stoa-web PRs #5, #6, #7
- [x] CAB-1133: Portal Test Suite (34 pts) — PR #461, 505 tests
- [x] CAB-1134: ADR-040 Born GitOps (5 pts) — stoa-docs PR #17
- [x] CAB-1138: GitOps Operator P1-P6 (21 pts) — PRs #415-#472, deployed 0.3.0
- [x] CAB-1030: Admin Guide & Onboarding Ops Ready (13 pts) — PR #475
- [x] CAB-1169: AI Factory v2 (13 pts) — PRs #474, #476
- [x] CAB-1135: AWS Decommissioning (P2) — OVH+Hetzner live, 92% cost reduction
- [x] CAB-1166: 4-Persona Test Parity (29 pts) — PRs #467, #468
- [x] Arena k6 Migration L1+L2+L3 — PRs #438, #444, #447, #449, #480 (ramp-up + CI95 bars)
- [x] CAB-1035: Persona Alex DX Test (2 pts) — PR #488 (NO-GO, TTFTC=infinite, 4 friction tickets)
- [x] CAB-1174: AI Factory v2 autonomous pipeline (13 pts) — PRs #496-#516
- [x] CAB-1175: Status Page MVP Upptime (8 pts) — stoa-platform/status repo, Council 8.50/10
- [x] CAB-1182: CONTRIBUTING.md + PR/Issue Templates (3 pts) — PR #525
- [x] CAB-1152: Community Infrastructure EPIC (P1) — PR #525
- [x] CAB-710: n8n + STOA AI Gateway Demo "ESB is Dead" (3 pts) — PR #517
- [x] CAB-1150: Preparation Demo 24/02 — narrative + speaker notes (8 pts) — PR #501
- [x] CAB-1129: Demo Script — Design Partner Pitch 5min (5 pts) — PR #506
- [x] CAB-1130: Demo Slides — Design Partner Presentation (8 pts) — PR #509, 10 Marp slides
- [x] CAB-1075: Demo Day Ready — Freeze + Dry Run + Plan B/C (5 pts) — PR #513
- [x] CAB-1148: Staging Freerun — AI Guardrails + Fallback Chain (13 pts) — PR #495
- [x] CAB-707: Guardrails — PII Detection & Prompt Injection (5 pts) — PR #495
- [x] CAB-708: Fallback Chain — Resilience multi-provider (3 pts) — PR #495
- [x] CAB-1145: Smoke test complet parcours demo PROD (P1)
- [x] CAB-1147: Benchmarks Freeze — STOA vs Kong vs Gravitee (P2)
- [x] +14 sub-issues (docs mega PRs, sidebar redesign, kyverno, SEO, sidecar ADR)

---

## Cycle 8 (Feb 16–22) — CURRENT

**Scope**: 339 pts (active) | **Done**: 100 pts (29%) | **Velocity**: 25 issues closed
**Theme**: Demo finale + Staging V1++ + DX Remediation + Community Launch Prep + SaaS MVP
**Fill-cycle**: +13 Quick Wins promoted (2026-02-15); +30 backlog items promoted to cycle (2026-02-16, 526 pts)
**Backlog in cycle**: ~604 pts (18 new MEGAs + 12 strategic/business items + legacy parked)

### Done (25 issues)

- [x] CAB-353: Go/No-Go Checklist 3 Months (5 pts) — PR #482 (9.00/10 → GO)
- [x] CAB-1146: Baseline PROD — Documenter etat de reference avant freeze (P1)
- [x] CAB-1170: [DX] Enable Keycloak self-registration (5 pts) — PRs #529, #530 (Council 8.50/10)
- [x] CAB-1172: [DX] Auto-approve free-tier subscriptions (3 pts) — PR #534 (Council 8.50/10)
- [x] CAB-1185: [Portal] Try-It Form Schema Validation (3 pts) — PR #557 (Council 8.25/10)
- [x] CAB-1186: [E2E] Unskip Demo Showcase Feature (3 pts) — PR #553
- [x] CAB-1171: [DX] Quick Start rewrite — single golden path (3 pts) — stoa-docs PR #46
- [x] CAB-1173: [DX] MCP guide for developers — zero kubectl (3 pts) — stoa-docs PR #46
- [x] CAB-1188: [SaaS] MCP SaaS Self-Service MVP (34 pts) — PRs #545, #549, #550, #551
  - [x] CAB-1249: [API] BackendApi + SaasApiKey models+CRUD (13 pts) — PR #545
  - [x] CAB-1250: [Gateway] BYOK credential proxy + tenant tools (8 pts) — PR #549
  - [x] CAB-1251: [UI] Console SaaS Backend APIs + API Keys (10 pts) — PR #550
  - [x] CAB-1252: [E2E] SaaS BDD tests (3 pts) — PR #551
- [x] CAB-1153: Activer GitHub Discussions (1 pt)
- [x] CAB-1155: FUNDING.yml — Activer GitHub Sponsors
- [x] CAB-1156: Labelliser 10 issues "good first issue" (1 pt)
- [x] CAB-1157: Announcement Bar Docusaurus
- [x] CAB-1158: README Badges + Contributors Wall (1 pt)
- [x] CAB-1321: [Portal] Fix Terms of Service link (3 pts) — PR #561 + stoa-docs PR #47
- [x] CAB-1183: [Gateway] Sidecar Mode P1 — ext_authz Enforcement Layer (8 pts) — PR #555
- [x] CAB-1184: [Adapter] Apigee Gateway Adapter P1 — Google Cloud CRUD (5 pts) — PR #556
- [x] CAB-362: GW2-10 Circuit Breaker + Retry (5 pts) — PR #558
- [x] CAB-1149: Staging Freerun — V1++ (13 pts) — meta-ticket, 5 sub-PRs merged
- [x] CAB-1162: SEO Tracking — Looker Studio + Search Console archive (3 pts) — PR #564
- [x] CAB-1187: [SEO] Blog Batch 7 — 5 Articles Week of Feb 17 (8 pts) — stoa-docs PR #48

### In Progress

- [~] CAB-802: Dry Run + Script + Video (3 pts, P1)
  - ✅ demo-dry-run.sh rewritten: 8 acts, 23 checks, GO/NO-GO (PR #456)
  - ✅ 7 production fixes: 23/23 PASS, GO in 3.5s (PR #463)
  - ✅ Credential fixes (PR #469)
  - [ ] Repetition #1 (mercredi 19) — timer 5 min
  - [ ] Repetition #2 (vendredi 21) — avec Cedric comme temoin
  - [ ] Video backup filmee
- [~] CAB-1154: Algolia DocSearch — Soumettre candidature (1 pt, P1)

### Todo

- [ ] CAB-1151: Dress Rehearsal — Smoke test final PROD (3 pts, P1)
- [ ] CAB-1128: Design Partner Communication — Client A Beta Access (3 pts, P2)
- [ ] CAB-709: UAC for LLM — Contrats unifies pour backends IA (5 pts, P2) — DEFERRED (archived)

### Backlog — DX Remediation (from CAB-1035 friction analysis) ✅ ALL DONE

- [x] CAB-1170: [DX] Enable Keycloak self-registration (5 pts, P1) — PRs #529, #530 (Council 8.50/10)
- [x] CAB-1171: [DX] Quick Start rewrite — single golden path (3 pts, P2) — stoa-docs PR #46
- [x] CAB-1172: [DX] Auto-approve free-tier subscriptions (3 pts, P2) — PR #534 (Council 8.50/10)
- [x] CAB-1173: [DX] MCP guide for developers — zero kubectl (3 pts, P2) — stoa-docs PR #46

### Backlog — Community Infrastructure (CAB-1152 sub-tickets) — 5/6 Done

- [x] CAB-1153: Activer GitHub Discussions (1 pt, P1)
- [~] CAB-1154: Algolia DocSearch — Soumettre candidature (1 pt, P1)
- [x] CAB-1155: FUNDING.yml — Activer GitHub Sponsors (P2)
- [x] CAB-1156: Labelliser 10 issues "good first issue" (1 pt, P1)
- [x] CAB-1157: Announcement Bar Docusaurus (P2)
- [x] CAB-1158: README Badges + Contributors Wall (1 pt, P1)

### Backlog — Promoted by /fill-cycle (2026-02-15)

- CAB-1177: [Phase 1] Kafka Central Nervous System — 8 Topic Families & Sinks (8 pts, P2) — Council 7.50/10
- CAB-1178: [Phase 2] Kafka → SSE Bridge — Consumer Adapter Multi-Tenant (5 pts, P2) — blocked by CAB-1177
- CAB-1179: [Phase 3] MCP Notifications — Agent Push & Subscription Model (5 pts, P2) — blocked by CAB-1178
- ~~CAB-1180: [Phase 4] Event-Driven Governance — CQRS, Sagas & Policy Propagation (8 pts, P3) — deferred to Cycle 10+ per Council~~
- CAB-1124: [Business] Modele ESN Partner — Structure Commerciale via Partenaires (5 pts, P2)
- CAB-1125: [Comm] Video Punchline AI Factory — Velocite + Branding Communaute (8 pts, P2)

### Backlog — Auto-promoted by /fill-cycle --auto (2026-02-15)

- CAB-1132: [Strategic] Business Model Validation — Post Demo Feb 24 (8 pts, P1)
- CAB-758: Simulation Architecte — Entrainement Q/R (3 pts)
- CAB-760: MVP n8n — Spaced Repetition Personnel (8 pts)
- CAB-1126: [Comm] Demo Video Courte STOA — Self-Service API Management (8 pts, P2)
- CAB-1127: [Comm] Dual-Track Content — Demo Client + Communaute Landing Page (5 pts, P2)
- CAB-1163: ADR-043 — Strategic Positioning: Meta-Gateway for Agentic Infra (5 pts, P4)

### Backlog — Council-Validated MEGAs (2026-02-16)

- [ ] CAB-1289: [MEGA] Gateway Test Coverage & Quality — 27 Untested Modules (34 pts, P3) — Council 8.75/10
- [ ] CAB-1297: [MEGA] DX: Developer Experience — READMEs, .env.example, Onboarding (13 pts, P3) — Council 8.50/10
- [ ] CAB-1291: [MEGA] Platform: API Test Coverage & Quality — 44 Untested Modules (34 pts, P3) — Council 8.00/10
- [ ] CAB-1294: [MEGA] DX: Portal Test Coverage & UX Completion — 26 Untested Modules (21 pts, P3) — Council 8.00/10
- [ ] CAB-1290: [MEGA] Gateway: Live-Code Feature Completion — MCP Protocol + Observability (13 pts, P3) — Council 7.75/10
- [ ] CAB-1299: [MEGA] Roadmap: UAC Spec + Protocol Binders + Dynamic Routing (34 pts, P3) — Council 7.75/10
- [ ] CAB-1292: [MEGA] Platform: API Auth Completion — KC Clients, IAM Sync, Security Fix (21 pts, P3) — Council 7.50/10
- [ ] CAB-1295: [MEGA] DX: Console Test Coverage & UX Completion — 23 Untested Modules (21 pts, P3) — Council 7.50/10
- [ ] CAB-1300: [MEGA] Platform: API Runtime Completion — Events, Deployments, Contracts, MCP RBAC (13 pts, P3) — Council 7.50/10
- [ ] CAB-1293: [MEGA] Platform: K8s Production Hardening — SecurityContext, NetworkPolicy, Rollout (13 pts, P3) — Council 7.25/10
- [ ] CAB-1298: [MEGA] Platform: Tech Debt Cleanup — Lint Suppressions Audit & Auth Module Docs (13 pts, P3) — Council 7.25/10
- ~~CAB-1296: [MEGA] DX: E2E Test Expansion — Canceled (Council 5.50/10, fictional scope)~~

### Backlog — Promoted Strategic + Business (2026-02-16)

- CAB-593: [Epic] Configurable Onboarding Workflows Engine (34 pts, P1)
- CAB-1068: [MEGA] AI Factory Setup — Claude Code H24 + Orchestration (3 pts, P1)
- CAB-1176: [MEGA] Kafka → MCP Event Bridge — Event-Driven AI-Native APIM (26 pts, P2)

### Backlog — Promoted MEGA Tickets (2026-02-16) — 18 new, 406 pts

**Platform** (178 pts):
- CAB-1301: [MEGA] Platform: Cilium Network Foundation — Gateway API + NetworkPolicy (34 pts)
- CAB-1303: [MEGA] Platform: Multi-Environment STAGING — Promote Workflow (21 pts)
- CAB-1307: [MEGA] Platform: Ticketing ITSM — Promotion Request Workflow (34 pts)
- CAB-1308: [MEGA] Platform: Resource Lifecycle Management — Tagging + Cleanup + Alerts (34 pts)
- CAB-1309: [MEGA] Platform: Resource Lifecycle Advanced — Quotas + Self-Service TTL (34 pts)
- CAB-1310: [MEGA] Platform: Jenkins Orchestration Layer — JCasC + Pipelines + Kafka (34 pts)
- CAB-1315: [MEGA] Platform: Automated Tenant Provisioning — "One API Call" Onboarding (21 pts)

**Gateway** (97 pts):
- CAB-1305: [MEGA] Gateway: Security Jobs Pipeline — Trivy + Gitleaks + CIS Benchmarks (21 pts)
- CAB-1313: [MEGA] Gateway: Enterprise MCP Federation — Multi-Dev/Agent Master Account (34 pts)
- CAB-1314: [MEGA] Gateway: MCP Skills System — Context Injection + Agent Integration (21 pts)
- CAB-1317: [MEGA] Gateway: MCP Proxy Hardening P3 — OAuth Flows + Lazy Discovery + CB (21 pts)

**DX** (47 pts):
- CAB-1306: [MEGA] DX: Portal Self-Service V2 — Catalog + Subscriptions + Onboarding (34 pts)
- CAB-1318: [MEGA] DX: Consumer Execution View — Error Taxonomy Dashboard (13 pts)

**Observability** (42 pts):
- CAB-1302: [MEGA] Observability: OpenSearch Monitoring Stack — Logging + Dashboards (21 pts)
- CAB-1316: [MEGA] Observability: Self-Diagnostic Engine + Hop Detection — Auto RCA (21 pts)

**Community** (47 pts):
- CAB-1304: [MEGA] Community: Demo Tenant Automation — Reset + Sample APIs (13 pts)
- CAB-1311: [MEGA] Community: GTM Strategy & Licensing — Open Core + Repo Structure (13 pts)
- CAB-1312: [MEGA] Community: GTM Docs + Community Channels + IBM Positioning (21 pts)

### Backlog — Long-term (parked in cycle, not committed)

- CAB-1181: [Docs] Interactive React Diagrams in Docusaurus (5 pts, P2)
- CAB-601: Status Page — superseded by CAB-1175
- CAB-571: Error Snapshot Network/TLS (P2)
- CAB-570: Error Snapshot Backend/NetworkPolicy (P2)
- CAB-392: Community Contrib Value Program (P3)
- CAB-252: STOA Gateway v2 — Linux Native
- CAB-251: Portal Full E2E Testing (P1)
- CAB-153: REST Protocol Binder
- CAB-151: Contract Transformer (OpenAPI/AsyncAPI ↔ UAC)
- CAB-149: Specification UAC v1.0 (R&D)
- CAB-3: Multi-environnement (P1)

---

## Cycle 9 (Feb 23–Mar 1) — NEXT

**Theme**: Post-Demo + Product Roadmap

### Backlog (no committed items yet)

- CAB-572: Portal Workflows — Subscriptions + Certs (P2)
- CAB-435: Owner Role — Strategic Portfolio View (P2)
- CAB-395: Adapter STOA → webMethods — Migration Bridge PoC (P3)
- CAB-158: Documentation R&D CIR

---

## Milestones

| Date | Event | Gate |
|------|-------|------|
| Dim 15 fev | Cycle 7 ends, PROD freeze | CAB-1145 + CAB-1146 ✅ |
| Lun-Mer 16-19 | Staging freerun V1++ | CAB-1149 |
| Jeu-Sam 20-22 | Off — narrative prep + rehearsals | CAB-802 |
| Dim 22 fev | Dress rehearsal | CAB-1151 |
| Mar 24 fev | DEMO DAY | 5 min live + "ESB is Dead" |

## KPIs Demo

| Metrique | Cible | Status |
|----------|-------|--------|
| Consumer flow E2E | Portal→Subscribe→Token→Call | ✅ CAB-1121 |
| mTLS use case client | 100+ certs, RFC 8705 | ✅ CAB-864 + CAB-872 |
| OpenAPI→MCP bridge | stoactl bridge demo | ✅ CAB-1137 |
| Error Snapshot | Provoquer + investiguer en live | ✅ CAB-550 |
| Dry run 2x sans bug | 5 min chrono | 🟡 CAB-802 (script done, rehearsals pending) |
| Plan SI post-demo | Arbre decision + roadmap | ✅ CAB-1031 |
| Docs site | Complet, 0 placeholder | ✅ 107 pts, 6 MEGAs |

## Regles

1. **Linear is source of truth** — plan.md is a view, not the master
2. Si bloque > 1h → contourner, noter, avancer
3. Code freeze PROD dimanche 15 a 18h
4. Staging freerun lundi-mercredi (no PROD changes)
5. Chaque session Claude Code = 1 sous-tache, pas plus
6. `/sync-plan` before and after each session
