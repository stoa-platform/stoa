# STOA Memory

> Derniere MAJ: 2026-02-24 (C9 802pts scope, 684pts C9-done (85.3%)) — W3 complete, veille system live

## ✅ DONE

> Full history: 1305+ pts across 88 issues (C8 alone). See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
- ✅ CAB-1347 [MEGA] Event-Driven V2 Phase 3 (Policy Propagation) — PRs #1032, #1034 (API+Gateway, stoa.policy.changes topic, 13 tests). Phases 1-2 (CQRS, Sagas) deferred per Council.
- ✅ CAB-1348 [MEGA] v2 Linux Native — CANCELLED (tokio-uring incompatible with #[tokio::main], Council 6.0)
- ✅ Veille concurrentielle 3 niveaux — PRs #1019, #1020, #1025
  - L1: competitive-watch skill + CLI script + n8n template (hebdo)
  - L2: monthly-ia-factory-audit GHA (14 dimensions/100, regression alerts)
  - L3: /benchmark-competitors command + competitive-analyst agent (trimestriel)
  - Q1 Benchmark: STOA 91/100, Cursor 62, Codex 48, Windsurf 38, Aider 35, Q Dev 32
- ✅ PR backlog cleanup: 4 factory PRs merged (#1008, #1006, #1004, #974), 3 stale closed (#1012, #977, #971)
- ✅ chore(deps): 6 Dependabot PRs merged (#961, #960, #958, #957, #955, #954)
- ✅ CAB-1446 [MEGA] Gateway Test Coverage Expansion (21 pts) — PR #995
- ✅ CAB-1456 [gateway] Metering enrichment + budget enforcement (5 pts) — PR #998
- ✅ Test Blitz: CAB-1448 PR #996 (320 tests), CAB-1451 PR #997 (E2E), CAB-1452 PR #984 (110 tests) — partial MEGAs
- ✅ CAB-1450 [MEGA] DX: CI & Local Dev Completeness (13 pts) — PRs #975, #983, #987, #989
- ✅ CAB-1342 [MEGA] Helm Auto-Sync Secrets + Multi-Staging (21 pts) — PR #990
- ✅ CAB-1334 [MEGA] Usage Metering Pipeline P1 (21 pts) — PR #991
- ✅ CAB-1438 [MEGA] K8s HPA + PDB for All Components (21 pts) — PR #970
- ✅ CAB-1439 [MEGA] Portal Component Test Coverage — 14 Untested (21 pts) — PR #968
- ✅ CAB-1316 [MEGA] Self-Diagnostic Engine + Hop Detection (21 pts) — PR #981
- ✅ CAB-1392 [MEGA] Security & MCP Deep-Dive Content (21 pts) — stoa-docs
- ✅ CAB-1440 [MEGA] E2E: Unblock @wip Features (13 pts) — PR #969
- ✅ CAB-1384 Landing i18n FR+EN (8 pts) — stoa-web
- ✅ CAB-1383 Docs i18n FR+EN (8 pts) — stoa-docs
- ✅ CAB-1444 i18n CI Quality Gate + Glossary (5 pts) — PR #976
- ✅ CAB-1322 [MEGA] Full UX Audit — Apple-Style (21 pts) — PR #892 (P1)
- ✅ CAB-289 Conversation History (5 pts) — PR #930
- ✅ CAB-605 Dynamic Tool Generation from UAC (8 pts) — PR #937
- ✅ CAB-606 Migrate Tools to New Schema + Aliases (5 pts) — PR #967
- ✅ CAB-1437 [MEGA] API Service Layer Hardening (21 pts) — PRs #912, #935, #963, #966
- ✅ CAB-1432 [MEGA] Credential Mapping (21 pts) — PRs #899 (API+GW), #903 (Portal UI)
  - P1: Backend API (7 CRUD, Fernet encryption, RBAC, 26 tests) + Gateway credential store
  - P2: Portal UI (table + modal + search + auth type switching, 38 tests)
- ✅ CAB-1393 [MEGA] Developer Onboarding Content (21 pts) — stoa-docs PR #82
- ✅ CAB-1345 [MEGA] WebSocket & Streaming — Bidirectional MCP (21 pts) — PR #890
- ✅ CAB-1319 [MEGA] MCP Developer Self-Service (21 pts) — PR #898 (3 phases, 77 tests, +3214 LOC)
- ✅ CAB-709 UAC for LLM — LLM contract types for UAC (5 pts) — PR #895
- ✅ CAB-287 Chat Agent Tool Injection with Agentic Loop (5 pts) — PR #894
- ✅ CAB-374 [MEGA] Vercel-Style DX — Git-First API Deployment (34 pts) — ALL 3 PHASES DONE
- ✅ CAB-1394 [MEGA] Community: SaaS Playbook Series (13 pts) — ALL 3 PHASES DONE
- ✅ CAB-1331 [MEGA] UAC-Driven Observability (21 pts) — ALL 3 PHASES DONE
- ✅ CAB-1336 [MEGA] Multi-Cloud Adapters — Apigee + AWS + Azure (21 pts) — ALL 3 DONE
- ✅ CAB-1123 [MEGA] Prompt Cache for HEGEMON AI Factory (21 pts) — PR #878
- ✅ CAB-286 Chat Agent Backend API — Anthropic Streaming (8 pts) — PR #889
- ✅ CAB-285 Chat Agent UI Component (8 pts) — PR #877
- ✅ CAB-1352 [docs] ADR-045: stoa.yaml Declarative API Spec (3 pts) — already existed in stoa-docs
- ✅ fix(docs): Vercel build fix — remove nested ajv overrides from stoa-docs (PR #78)
- ✅ chore: Model Policy update — Opus default for local impl, Sonnet for CI/subagents (PR #846)
- ✅ chore: 7 Dependabot PRs merged (#624, #623, #613, #609, #607, #603, #602) + 17 stale PRs closed
- ✅ fix(ci): Dependency Scan 3 failures → green — PR #843
- ✅ fix(gateway): OIDC port + startup probe — PR #840
- ✅ CAB-1390 [MEGA] Portal Component Test Coverage & Feature Fixes (21 pts) — ALL 3 PHASES DONE
- ✅ CAB-1333 [MEGA] MCP Protocol Full Compliance (34 pts) — PR #831
- ✅ CAB-1389 [MEGA] Cross-Component Quality Pass (13 pts) — ALL 3 PHASES DONE
- ✅ fix(gateway): Dockerfile rust:1.88→1.93 — PR #830
- ✅ fix(gateway): startup probe 33s→53s (PR #834)
- ✅ fix(gateway): STOA_KEYCLOAK_INTERNAL_URL hairpin NAT bypass — stoa-infra
- ✅ CAB-1388 [MEGA] API Test & Service Hardening Round 2 (21 pts) — PR #818
- ✅ CAB-1413 [cp-api] Notification Service — Kafka → Slack (3 pts) — PR #814
- ✅ CAB-1337 [MEGA] AI Guardrails V2 (34 pts) — PRs #809, #816, #825
- ✅ Gap #5 CP API Prometheus scraping — PRs #788, #793, #799
- ✅ AI Factory model migration — PR #804
- ✅ CAB-1391 [MEGA] Migration Guide Expansion (13 pts) — stoa-docs PR #68
- ✅ CAB-1301 [MEGA] Gateway API + NetworkPolicy (21 pts) — ALL 3 PHASES DONE
- ✅ CAB-1398 [MEGA] AI Factory Slack Upgrade + Dispatch Gap Fixes (26 pts) — ALL 4 PHASES DONE
- ✅ CAB-86 TTL Extension — PR #780
- ✅ Promote-to-prod workflow — PR #771
- ✅ Portal mock data fix — PR #771

### Cycle 8 (Feb 16-22) — CLOSED (1305 pts, 88 issues, 186 pts/day)

Top MEGAs: CAB-1299 UAC (34 pts), CAB-1313 Federation (34 pts), CAB-1289 GW Tests (34 pts),
CAB-1378 Test Blitz (34 pts), CAB-1323 Portal RBAC (34 pts), CAB-1188 SaaS MVP (34 pts),
CAB-593 Onboarding Workflows (34 pts), CAB-1291 API Tests (34 pts), CAB-374 Deploy Lifecycle (34 pts).
Also: CAB-1176 Kafka Event Bridge (26 pts, all phases done), CAB-1317 MCP Proxy P3 (21 pts),
CAB-1314 MCP Skills (21 pts), CAB-1332 Perf (21 pts), CAB-1292 Auth (21 pts), +40 more issues.

## 🔴 IN PROGRESS

CAB-802: Dry Run + Script + Video Backup (3 pts) — HUMAN ONLY
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
- ✅ Production validated: 23/23 PASS, GO in 5s
- [ ] Repetitions + video backup (human-only)

## 📋 NEXT

CAB-1132: Business Model Validation — Post Demo (8 pts, P1)
CAB-1126: Demo Video (8 pts, P2)
CAB-1125: Video Punchline AI Factory (8 pts, P2)
CAB-1127: Dual-Track Content (5 pts, P2)
CAB-1124: Modele ESN Partner (5 pts, P2)
CAB-1128: Design Partner Communication (3 pts, P2)

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 17 mars 2026
- docs.gostoa.dev = 41+ articles (Layer7 + webMethods guides live, all 8 migration spokes published)
- llms.txt + llms-full.txt: full migration guides + AI Factory sections live
- ADR numbering: stoa-docs owns numbers (001-050). Next: **ADR-051**
- Velocity C8: 1305 pts / 88 issues / 186 pts/day (final)
- Velocity C7: 505 pts / 44 issues / 72 pts/day
- Rolling avg: 129.3 pts/day (C7+C8)
- Portal MCP pages: MOCK_SERVERS removed (PR #771) — pages now use real API only
- MEGA Strike W1-W4: 11 tickets, 173 pts in single day (PRs #968-#991)
- Test Blitz + Metering: PRs #984, #996, #997, #998 (3 partial MEGAs + CAB-1456 done)
- MEGA Strike W3: CAB-1347 done (PRs #1032, #1034), CAB-1348 cancelled (tokio-uring infeasible)
- MEGA Strike W4 triage: 3 cancelled (CAB-1307, 1309, 1310 — off-mission), 2 kept (CAB-1304, 1311), 3 deferred (CAB-1308, 1324, 1402)
- PR hygiene: 10 merged, 3 stale closed, 3 deferred (OTel 0.31 breaking, TS-eslint 6→8 breaking)
- Veille system: L1 weekly (skill+CLI), L2 monthly (GHA audit), L3 quarterly (benchmark command+agent)
- Benchmark Q1 gaps: sandbox isolation (P1, Codex), plugin marketplace (P2, Cursor). Cursor copie patterns CC.
