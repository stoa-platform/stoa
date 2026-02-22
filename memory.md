# STOA Memory

> Derniere MAJ: 2026-02-22 (CAB-1333 PR #831; CAB-1389 done — PRs #810, #811, #820; fix Dockerfile Rust 1.93 PR #830; CAB-1388 PR #818)

## ✅ DONE

> Full history: 905+ pts across 88 issues (C8 alone). See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
- ✅ CAB-1333 [MEGA] MCP Protocol Full Compliance (34 pts) — PR #831
  - P1: spec coverage matrix (docs/mcp-spec-coverage.md)
  - P2: 4 missing methods (prompts/list, prompts/get, logging/setLevel, resources/read) + send_to_session
  - P3: 16 new conformance tests — 31/31 contract tests pass
- ✅ CAB-1389 [MEGA] Cross-Component Quality Pass (13 pts) — ALL 3 PHASES DONE
  - P1: Console Federation & Index Tests (PR #810) — 15 new test files, modals + wrappers
  - P2: Gateway Feature Wiring (PR #811) — ClassificationType, ApiState, JWT user_id extraction
  - P3: Gateway Lint Cleanup (PR #820) — builder pattern replaces clippy suppressions
- ✅ fix(gateway): Dockerfile rust:1.88→1.93 (floor_char_boundary stable in 1.93) — PR #830
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

### Cycle 8 (Feb 16-22) — CLOSED (905 pts, 88 issues, 129 pts/day)

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
- ADR numbering: stoa-docs owns numbers (001-048). Next: **ADR-049**
- Velocity C8: 905 pts / 88 issues / 129 pts/day (final)
- Velocity C7: 505 pts / 44 issues / 72 pts/day
- Rolling avg: 107.5 pts/day (C7+C8)
- Portal MCP pages: MOCK_SERVERS removed (PR #771) — pages now use real API only
