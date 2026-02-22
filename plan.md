# Sprint Plan — STOA Platform

> Auto-synced with Linear via `/sync-plan`. Source of truth: Linear cycles.
> Last sync: 2026-02-22 (/sync-plan)

## Cycle 8 (Feb 16–22) — CLOSED

**Scope**: 905 pts | **Done**: 905 pts (100%) | **Velocity**: 88 issues closed, 129 pts/day
**Theme**: Demo finale + Staging V1++ + DX Remediation + Community Launch Prep + SaaS MVP

### Done (88 issues)

**Gateway** (198 pts):
- [x] CAB-1313: [MEGA] Enterprise MCP Federation (34 pts) — 3 phases, 6 sub-PRs
- [x] CAB-1317: [MEGA] MCP Proxy Hardening P3 — OAuth + Lazy Discovery + CB (21 pts)
- [x] CAB-1314: [MEGA] MCP Skills System — Context Injection + Agent (21 pts) — 3 phases
- [x] CAB-1332: [MEGA] Performance Optimization — Sub-ms Proxy Overhead (21 pts)
- [x] CAB-1380: [MEGA] Shadow Mode & Federation Polish (21 pts)
- [x] CAB-1330: [MEGA] MCP Hot-Reload & CI Security Showcase (13 pts)
- [x] CAB-1305: [MEGA] Security Jobs Pipeline — Trivy + CIS (21 pts) — PRs #629-631
- [x] CAB-1289: [MEGA] Test Coverage & Quality — 27 Modules (34 pts) — PR #566
- [x] CAB-1290: [MEGA] Live-Code Feature Completion (13 pts) — PR #585
- [x] CAB-1359: Arena Performance — Close the Kong Gap (13 pts) — PRs #626, #632
- [x] CAB-1183: Sidecar Mode P1 — ext_authz (8 pts) — PR #555
- [x] CAB-362: Circuit Breaker + Retry (5 pts) — PR #558

**Platform** (318 pts):
- [x] CAB-1299: [MEGA] UAC Spec + Protocol Binders + Dynamic Routing (34 pts) — PRs #581-591
- [x] CAB-1292: [MEGA] API Auth Completion — KC + IAM + Security (21 pts) — PRs #594, #596
- [x] CAB-1291: [MEGA] API Test Coverage — 44 Modules (34 pts) — PRs #576, #582
- [x] CAB-1300: [MEGA] API Runtime Completion — Events + Contracts (13 pts) — PR #599
- [x] CAB-1293: [MEGA] K8s Hardening — SecurityContext + NetworkPolicy (13 pts) — PR #600
- [x] CAB-1379: [MEGA] K8s HPA, PDB & Auto-Scaling (21 pts)
- [x] CAB-1381: [MEGA] API Stubs Cleanup (13 pts) — PR #718
- [x] CAB-1298: [MEGA] Tech Debt Cleanup (13 pts) — PR #646
- [x] CAB-1315: [MEGA] Automated Tenant Provisioning (21 pts)
- [x] CAB-593: [Epic] Configurable Onboarding Workflows (34 pts)
- [x] CAB-1188: [MEGA] MCP SaaS Self-Service MVP (34 pts) — PRs #545-551
- [x] CAB-1177: Kafka CNS — 8 Topic Families (8 pts) — PR #601
- [x] CAB-1178: Kafka → SSE Bridge (5 pts)
- [x] CAB-1179: MCP Notifications — Agent Push (5 pts)
- [x] CAB-1176: [MEGA] Kafka → MCP Event Bridge (26 pts) — P1-P3 complete
- [x] CAB-497: Event Backbone Ops (8 pts)
- [x] CAB-498: Topics Sizing (5 pts)
- [x] CAB-499: Multi-tenant Quotas (3 pts)

**DX** (217 pts):
- [x] CAB-1378: [MEGA] Test Coverage Blitz — Console + Portal + API (34 pts)
- [x] CAB-1323: [MEGA] Portal Governance — Multi-Audience + RBAC (34 pts) — PRs #697, #714, #719
- [x] CAB-1325: [MEGA] Self-Onboarding Zero-Touch Trial (21 pts) — PR #732
- [x] CAB-1318: [MEGA] Consumer Execution View — Error Taxonomy (13 pts) — PR #762
- [x] CAB-1382: [MEGA] Code Hygiene Sprint (13 pts) — PRs #724-726
- [x] CAB-1295: [MEGA] Console Test Coverage (21 pts) — PR #590
- [x] CAB-1294: [MEGA] Portal Test Coverage (21 pts) — PR #580
- [x] CAB-1297: [MEGA] Developer Experience — READMEs + Onboarding (13 pts) — PR #577
- [x] CAB-1306: [MEGA] Portal Self-Service V2 (13 pts) — PRs #636, #638, #669
- [x] CAB-374: Deployment Lifecycle — API + UI + CLI + E2E (34 pts) — 3 repos

**Observability** (29 pts):
- [x] CAB-1386: AI Factory Observability (13 pts) — PRs #747, #750
- [x] CAB-1375: Grafana UAC Debug Dashboard (8 pts) — PR #763
- [x] CAB-1374: OTel Tracing with UAC Context (8 pts)

**AI Factory** (89 pts):
- [x] CAB-1367: Token Optimization — Rules Scoping + MEMORY Cleanup (13 pts) — PRs #666, #671
- [x] CAB-1368: Autonomous Self-Feeding Pipeline (21 pts)
- [x] CAB-1360: AI Factory v3 — Multi-Instance Hardening (13 pts)
- [x] CAB-1377: Slack Observability — Rich Notifications (13 pts)
- [x] CAB-1385: SEO Automation — Content Pipeline (13 pts)
- [x] CAB-1358: H24 Autonomous Activation (13 pts) — PR #589
- [x] CAB-1068: AI Factory Setup (3 pts)

**Community & Content** (25 pts):
- [x] CAB-1187: Blog Batch 7 — 5 Articles (8 pts)
- [x] CAB-1369: SEO Quick Wins (8 pts)
- [x] CAB-1181: Interactive Diagrams (5 pts) — stoa-docs PRs #52-58
- [x] CAB-1162: SEO Tracking (3 pts) — PR #564
- [x] CAB-1154: Algolia DocSearch LIVE (1 pt)

**Demo & Ops** (29 pts):
- [x] CAB-1151: Dress Rehearsal PROD — GO (3 pts)
- [x] CAB-1149: Staging Freerun V1++ (13 pts)
- [x] CAB-1184: Apigee Adapter P1 (5 pts) — PR #556
- [x] CAB-353: Go/No-Go Checklist (5 pts) — PR #482
- [x] CAB-1185: Portal Try-It Validation (3 pts) — PR #557
- [x] CAB-1373: Federation E2E Tests (5 pts) — PR #764
- [x] CAB-1321: Portal ToS Link Fix (3 pts) — PR #561
- [x] CAB-1186: Unskip Demo Feature (3 pts) — PR #553
- [x] CAB-1387: Ask-mode Slack Fix (2 pts)
- [x] CAB-1171: Quick Start Rewrite (3 pts) — stoa-docs PR #46
- [x] CAB-1173: MCP Guide Zero-kubectl (3 pts) — stoa-docs PR #46
- [x] +6 community infra sub-tickets (Discussions, Sponsors, Good First Issues, etc.)

**Gap Fixes** (9 pts):
- [x] CAB-1409: feat(uac): wire deploy_contract() in enable-binding (4 pts) — PR #802
- [x] CAB-1408: fix(observability): ServiceMonitor CP API Prometheus scraping (2 pts) — PR #799
- [x] CAB-1407: fix(observability): metric name drift SLO rules (2 pts)
- [x] CAB-1406: fix(portal): MCP Servers path mismatch (1 pt)

---

## Cycle 9 (Feb 23–Mar 1) — CURRENT

**Scope**: 118 pts (committed) | **Done**: 31 pts
**Theme**: Post-Demo + Product Roadmap + Community Content

### In Progress

- [~] CAB-802: Dry Run + Script + Video (3 pts, P1) — HUMAN ONLY
  - ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
  - ✅ Production validated: 23/23 PASS, GO in 5s
  - [ ] Repetitions + video backup (human-only)
### Done (2)
- [x] CAB-86: TTL Extension — Self-Service (5 pts) — PR #780
- [x] CAB-1398: [MEGA] AI Factory Slack Upgrade + Dispatch Gap Fixes (26 pts, P2) — PRs #768, #775, #781, #792, #795
  - [x] Phase 1: Dispatch Fixes — PR #768
  - [x] Phase 2: Slack Bot API dual-path — PR #775
  - [x] Phase 3: Slack Threading + Reactions — PR #781
  - [x] Phase 4: /stoa slash command + gap fixes — PRs #792, #795

### Todo
- [ ] CAB-1132: Business Model Validation — Post Demo 17 Mars (8 pts, P1)
- [ ] CAB-1126: Demo Video Courte STOA (8 pts, P2)
- [ ] CAB-1125: Video Punchline AI Factory (8 pts, P2)
- [ ] CAB-1127: Dual-Track Content — Demo Client + Landing (5 pts, P2)
- [ ] CAB-1124: Modele ESN Partner (5 pts, P2)
- [ ] CAB-1128: Design Partner Communication — Client A (3 pts, P2)
- [ ] CAB-709: UAC for LLM — Contrats unifiés pour backends IA (5 pts, P2)
- [ ] CAB-285: Chat Agent UI Component (8 pts, P2)
- [ ] CAB-286: Chat Agent Backend API (8 pts, P2)
- [ ] CAB-287: Chat Agent Tool Injection (5 pts, P2)
- [ ] CAB-288: Chat Agent Token Metering (5 pts, P2)
- [ ] CAB-1383: Docs i18n FR+EN (8 pts, P2)
- [ ] CAB-1384: Landing i18n FR+EN (8 pts, P2)

### Backlog — New MEGAs

**Gateway** (110 pts):
- CAB-1337: [MEGA] AI Guardrails V2 — Content Filtering + Token Budgets (34 pts)
- CAB-1333: [MEGA] MCP Protocol Full Compliance — Spec Parity (34 pts)
- CAB-1345: [MEGA] WebSocket & Streaming — Bidirectional MCP (21 pts)
- CAB-1348: [MEGA] v2 Linux Native — eBPF + io_uring (21 pts)

**Platform** (178 pts):
- CAB-1388: [MEGA] API Test Hardening Round 2 (21 pts)
- CAB-1389: [MEGA] Cross-Component Quality Pass (13 pts)
- CAB-1347: [MEGA] Event-Driven V2 — CQRS + Sagas (34 pts)
- CAB-1342: [MEGA] Helm Auto-Sync Secrets (21 pts)
- CAB-1336: [MEGA] Multi-Cloud Adapters — Apigee + AWS + Azure (34 pts)
- CAB-1334: [MEGA] SaaS Multi-Tier Billing — Stripe (34 pts)
- CAB-1324: [MEGA] Runtime Data Governance (21 pts)

**DX** (76 pts):
- CAB-1390: [MEGA] Portal Component Test Coverage (21 pts)
- CAB-1338: [MEGA] Portal i18n (21 pts)
- CAB-1322: [MEGA] Full UX Audit — Apple-Style (34 pts)

**Observability** (42 pts):
- CAB-1331: [MEGA] UAC-Driven Observability (21 pts)
- CAB-1316: [MEGA] Self-Diagnostic Engine + Hop Detection (21 pts)

**Community** (124 pts):
- CAB-1394: [MEGA] SaaS Playbook Series (13 pts)
- CAB-1393: [MEGA] Developer Onboarding Content (21 pts)
- CAB-1392: [MEGA] Security & MCP Deep-Dive Content (21 pts)
- [x] CAB-1391: [MEGA] Migration Guide Expansion — Axway, WSO2, Layer7 (13 pts) — stoa-docs PR #68 + stoa-web PR #10
- CAB-1329: [MEGA] Demo Content Library — 8 Themes (34 pts)
- CAB-1327: [MEGA] Docs as Code — RAG Chatbot (21 pts)

**Other**:
- CAB-1319: [MEGA] MCP Developer Self-Service (21 pts)
- CAB-1320: [MEGA] Repo Consolidation (21 pts)
- CAB-1312: [MEGA] GTM Docs + Community Channels (21 pts)
- CAB-1123: Prompt Cache for HEGEMON (21 pts)
- [~] CAB-374: [MEGA] Vercel-Style DX (34 pts) — Council 8.25/10 ✅ — 2 phases
  - **Phase 1** (parallel) [owner: —]
    - [ ] CAB-1410 [cp-api] stoa.yaml spec + deployment lifecycle API (13 pts)
    - [ ] CAB-1411 [docs] stoa.yaml spec v1.0 reference + CLI guide (5 pts)
  - **Phase 2** (after Phase 1) [owner: —]
    - [ ] CAB-1412 [stoactl] Audit + complete CLI commands (13 pts)
    - [ ] CAB-1413 [cp-api] Notification Service — Kafka → Slack (3 pts)

### Backlog — Legacy (parked)

- [x] CAB-1301: [MEGA] Gateway API + NetworkPolicy Foundation (21 pts, rescoped) — ALL 3 PHASES DONE
  - [x] CAB-1399 [infra] Gateway API CRDs + NGINX Gateway Fabric (8 pts) — PR #785
  - [x] CAB-1400 [infra] Ingress → HTTPRoute Migration (8 pts) — PR #791
  - [x] CAB-1401 [infra] Default-Deny NetworkPolicy (5 pts) — PR #797
- CAB-1402: [infra] Cilium CNI Foundation — Deferred (13 pts, blocked: MKS Standard GA)
- CAB-1303: [MEGA] Multi-Environment STAGING (21 pts)
- CAB-1307: [MEGA] Ticketing ITSM (34 pts)
- CAB-1308: [MEGA] Resource Lifecycle Management (34 pts)
- CAB-1309: [MEGA] Resource Lifecycle Advanced (34 pts)
- CAB-1310: [MEGA] Jenkins Orchestration Layer (34 pts)
- CAB-1304: [MEGA] Demo Tenant Automation (13 pts)
- CAB-1311: [MEGA] GTM Strategy & Licensing (13 pts)

---

## Milestones

| Date | Event | Gate |
|------|-------|------|
| Dim 22 fev | Cycle 8 closed | 905 pts, 88 issues |
| Mar 17 mars | DEMO DAY | 5 min live + "ESB is Dead" |
| Dim 1 mars | Cycle 9 ends | Post-Demo roadmap |

## KPIs Demo

| Metrique | Cible | Status |
|----------|-------|--------|
| Consumer flow E2E | Portal→Subscribe→Token→Call | ✅ CAB-1121 |
| mTLS use case client | 100+ certs, RFC 8705 | ✅ CAB-864 + CAB-872 |
| OpenAPI→MCP bridge | stoactl bridge demo | ✅ CAB-1137 |
| Error Snapshot | Provoquer + investiguer en live | ✅ CAB-550 |
| Dry run 2x sans bug | 5 min chrono | ✅ Script GO (23/23 PASS) |
| Plan SI post-demo | Arbre decision + roadmap | ✅ CAB-1031 |
| Docs site | Complet, 0 placeholder | ✅ 107 pts, 6 MEGAs |

## Regles

1. **Linear is source of truth** — plan.md is a view, not the master
2. Si bloque > 1h → contourner, noter, avancer
3. Chaque session Claude Code = 1 sous-tache, pas plus
4. `/sync-plan` before and after each session
