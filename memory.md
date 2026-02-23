# STOA Memory

> Derniere MAJ: 2026-02-23 (CAB-1338 i18n MEGA DONE — C9 333/523 pts)

## ✅ DONE

> Full history: 1305+ pts across 88 issues (C8 alone). See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
- ✅ CAB-374 [MEGA] Vercel-Style DX — Git-First API Deployment (34 pts) — ALL 3 PHASES DONE
  - P1: API deploy log streaming + SSE (PRs #850, #852) — CAB-1420, CAB-1421
  - P2: Console live deployment dashboard (PR #856) — CAB-1422
  - P3: E2E deploy flow BDD scenarios — SSE + rollback (PR #859) — CAB-1423
- ✅ CAB-1394 [MEGA] Community: SaaS Playbook Series (13 pts) — ALL 3 PHASES DONE
  - P1: Parts 1-2 + SMB Buying Guide (stoa-docs PR #75) — 3 articles, 4000+ words
  - P2: Parts 3-5 (stoa-docs PR #76) — 3 articles, production checklist
  - P3: Build vs Buy + series polish (stoa-docs PR #77, stoa-web PR #12) — cross-links + llms.txt
  - 7 articles total, complete series nav in each, llms.txt updated
- ✅ CAB-1331 [MEGA] UAC-Driven Observability (21 pts) — ALL 3 PHASES DONE
  - P1: OTel feature + UAC span enrichment (PR #870) — CAB-1424
  - P2: UAC Debug Dashboard — per-tool drill-down (PR #870) — CAB-1425
  - P3: Hybrid multi-cluster observability view (PR #884) — CAB-1426
- ✅ CAB-1336 [MEGA] Multi-Cloud Adapters — Apigee + AWS + Azure (21 pts) — ALL 3 DONE
  - Apigee v2 (PRs #556, #879), AWS API GW (PR #855), Azure APIM (PR #873)
- ✅ CAB-1123 [MEGA] Prompt Cache for HEGEMON AI Factory (21 pts) — PR #878
  - PromptCache struct + 5 admin endpoints + 3 MCP tools + file watcher
- ✅ CAB-285 Chat Agent UI Component (8 pts) — PR #877
- ✅ CAB-1352 [docs] ADR-045: stoa.yaml Declarative API Spec (3 pts) — already existed in stoa-docs
- ✅ fix(docs): Vercel build fix — remove nested ajv overrides from stoa-docs (PR #78)
- ✅ chore: Model Policy update — Opus default for local impl, Sonnet for CI/subagents (PR #846)
  - Data-driven: 44% Sonnet sessions >1h (some 4.5h), same tasks <15min with Opus at lower total cost
  - Local: Opus (impl) / Sonnet (subagents, mechanical) / Haiku (Explore, scan)
  - CI: unchanged (Sonnet — lighter context, no looping)
- ✅ chore: 7 Dependabot PRs merged (#624, #623, #613, #609, #607, #603, #602) + 17 stale PRs closed
- ✅ fix(ci): Dependency Scan 3 failures → green — PR #843
  - CVE-2024-23342 (ecdsa Minerva): --ignore-vuln on pip-audit (cp-api + mcp-gateway)
  - mcp-gateway archived path fix (archive/mcp-gateway/ fallback)
  - GHSA-3ppc-4f35-3m26 (minimatch ReDoS in @typescript-eslint): --omit=dev on npm audit
- ✅ fix(gateway): OIDC port + startup probe — PR #840 → pods finally 1/1 Running (3-session fix chain: #819 code → #835 apply-manifest → #840 port:8080 + probe)
- ✅ CAB-1390 [MEGA] Portal Component Test Coverage & Feature Fixes (21 pts) — ALL 3 PHASES DONE
  - P1: Critical components (PR #833) — Onboarding, Contracts, Apps test files
  - P2: Dashboard + Usage + Layout (PR #836) — 15 test files, 1094 LOC
  - P3: APICard + bugfixes + placeholder cleanup (PR #838) — certificateValidator fix
- ✅ CAB-1333 [MEGA] MCP Protocol Full Compliance (34 pts) — PR #831
  - P1: spec coverage matrix (docs/mcp-spec-coverage.md)
  - P2: 4 missing methods (prompts/list, prompts/get, logging/setLevel, resources/read) + send_to_session
  - P3: 16 new conformance tests — 31/31 contract tests pass
- ✅ CAB-1389 [MEGA] Cross-Component Quality Pass (13 pts) — ALL 3 PHASES DONE
  - P1: Console Federation & Index Tests (PR #810) — 15 new test files, modals + wrappers
  - P2: Gateway Feature Wiring (PR #811) — ClassificationType, ApiState, JWT user_id extraction
  - P3: Gateway Lint Cleanup (PR #820) — builder pattern replaces clippy suppressions
- ✅ fix(gateway): Dockerfile rust:1.88→1.93 (floor_char_boundary stable in 1.93) — PR #830
- ✅ fix(gateway): startup probe 33s→53s (PR #834 in stoa, stoa-infra commit a20eb47)
- ✅ fix(gateway): STOA_KEYCLOAK_INTERNAL_URL hairpin NAT bypass — stoa-infra commits 04efdb6+dca8f67
  - ArgoCD uses stoa-infra/charts/stoa-gateway, NOT stoa/stoa-gateway/k8s/deployment.yaml
  - Both pods 1/1 Running, 0 restarts (RS 54c5c6c949)
- ✅ CAB-1388 [MEGA] API Test & Service Hardening Round 2 (21 pts) — PR #818 (30 test modules, 80% coverage)
- ✅ CAB-1413 [cp-api] Notification Service — Kafka → Slack deployment fanout (3 pts) — PR #814
- ✅ CAB-1337 [MEGA] AI Guardrails V2 — Content Filtering + Token Budgets + Policy Engine (34 pts)
  - P0: ADR + OPA eval (PR #807 ADR), P1: ContentFilter (PR #809), P2: TokenBudget (PR #816), P3: GuardrailPolicy CRD (PR #825)
  - P1: BLOCKED/SENSITIVE regex classification + response-path scanning + guardrails/mod.rs
  - P2: TokenBudgetTracker (sliding-window per-tenant, 429 on exceed, warn at 80%)
  - P3: GuardrailPolicy CRD + store + K8s watcher + per-tenant resolution + tool allowlist
- ✅ Gap #5 CP API Prometheus scraping — PRs #788, #793, #799
  - ServiceMonitor (Helm), fix generate_latest(REGISTRY), NetworkPolicies port 8000
  - Prometheus targets: 2/2 health: up ✅
- ✅ AI Factory model migration — PR #804 (7 workflows + model-router.sh → claude-sonnet-4-6)
- ✅ CAB-1391 [MEGA] Migration Guide Expansion (13 pts) — stoa-docs PR #68 ✅ merged, stoa-web PR #10 ✅ merged
- ✅ CAB-1301 [MEGA] Gateway API + NetworkPolicy (21 pts) — ALL 3 PHASES DONE
  - P1: CRDs + NGF (PR #785), P2: HTTPRoutes + DNS cutover (PR #791), P3: NetworkPolicies (PR #797)
  - New LB: 92.222.226.6, 30 NetworkPolicies, 9 HTTPRoutes, 8 DNS records updated
- ✅ CAB-1398 [MEGA] AI Factory Slack Upgrade + Dispatch Gap Fixes (26 pts) — ALL 4 PHASES DONE
  - P1: Dispatch fixes (PR #768), P2: Bot API dual-path (PR #775), P3: Threading+Reactions (PR #781), P4: /stoa+gaps (PRs #792, #795)
- ✅ CAB-86 TTL Extension — PR #780 (PATCH /v1/subscriptions/{id}/ttl, migration 035, 11 tests, +616 LOC)
- ✅ AI Factory Slack Bot threading — PR #775 (Bot API dual-path, n8n sequential pipeline, thread_ts propagation)
- ✅ Promote-to-prod workflow — PR #771 (reusable-promote.yml + promote-to-prod.yml + runbook)
- ✅ Portal mock data fix — PR #771 (removed MOCK_SERVERS fallback from MCP pages, -189 LOC)

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
- docs.gostoa.dev = 40 articles (Layer7 + webMethods guides live, all 8 migration spokes published)
- llms.txt + llms-full.txt: full migration guides + AI Factory sections live
- ADR numbering: stoa-docs owns numbers (001-050). Next: **ADR-051**
- Velocity C8: 1305 pts / 88 issues / 186 pts/day (final)
- Velocity C7: 505 pts / 44 issues / 72 pts/day
- Rolling avg: 129.3 pts/day (C7+C8)
- Portal MCP pages: MOCK_SERVERS removed (PR #771) — pages now use real API only
