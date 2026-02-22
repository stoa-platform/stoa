# STOA Memory

> Dernière MAJ: 2026-02-22 (Portal mock data fix — PR #771 merged + CD verified)

## ✅ DONE

> Full history: 548+ pts across 59+ issues. See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
- ✅ Portal mock data fix — PR #771 (removed MOCK_SERVERS fallback from MCP pages, -189 LOC)

### Cycle 8 (Feb 16-22) — Recent
- CAB-1306: Portal Self-Service V2 (13 pts) — PRs #636, #638, #669 (3 phases)
- CAB-1298: Tech Debt Cleanup (13 pts) — PR #646
- CAB-1317: MCP Proxy Hardening P3 (21 pts) — PRs #639, #642, #647
- CAB-1367: AI Factory Token Optimization P1+P2 (13 pts) — PRs #666, #671
- CAB-1359: Arena Performance (13 pts) — PRs #626, #632
- CAB-1305: Security Jobs Pipeline (21 pts) — PRs #629, #630, #631
- CAB-1381: API Stubs Cleanup (13 pts) — PR #718 (20 TODO stubs → real implementations, 40 new tests)
- CAB-1323: Portal Multi-Audience + RBAC (34 pts MEGA) — PRs #697, #714, #719 (3 phases, ~917 LOC, 78 tests)
- CAB-1314: MCP Skills System MEGA (21 pts) — P1 PR #702, P2 PR #721, P3 PR #710 (3 phases, skills CSS cascade + context injection)
- CAB-1382: Code Hygiene Sprint (13 pts) — PRs #724, #725, #726 (P1: 38 dead_code removed, P2: 20→0 ESLint warnings + error tracking stub)
- CAB-1325: DX Self-Onboarding Zero-Touch Trial (21 pts MEGA) — PR #732 (3 phases: onboarding flow + trial API key + sandbox tools + funnel analytics)
- CAB-1318: Consumer Execution View — Error Taxonomy Dashboard (13 pts) — PR #762
- CAB-1151: Dress Rehearsal PROD (3 pts) — PROD GO (all pods healthy, ArgoCD synced, health endpoints 200)
- CAB-1375: Grafana UAC Debug Dashboard (8 pts) — PR #763 (12 panels, 4 rows: tool perf, tenant breakdown, rate limits, security)
- CAB-1373: Federation E2E Tests (5 pts) — PR #764 (15 BDD scenarios: 10 Console + 5 Gateway, @wip)
- CAB-1386: AI Factory Observability (13 pts) — PRs #747, #750 (state drift fix — already merged)
- CAB-1330: MCP Hot-Reload (13 pts) — P1 PR #727 (CRD watcher → SSE tools/list_changed). P2 deferred

## 🔴 IN PROGRESS

CAB-802: Dry Run + Script + Video Backup (3 pts) — HUMAN ONLY
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
- ✅ Production validated: 23/23 PASS, GO in 5s
- [ ] Répétitions + video backup (human-only)

## 📋 NEXT

(rien — Cycle 8 closed, remaining items are human-only)

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 17 mars 2026
- docs.gostoa.dev = 37 articles, 0 "Coming Soon"
- ADR numbering: stoa-docs owns numbers (001-048). Next: **ADR-049**
- Velocity C8: 703 pts / 73 issues (state drift fix: CAB-1330, CAB-1367 already Done on Linear)
- Portal MCP pages: MOCK_SERVERS removed (PR #771) — pages now use real API only
