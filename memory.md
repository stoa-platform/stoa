# STOA Memory

> Derniere MAJ: 2026-02-22 (state drift fix: CAB-1398 + CAB-86 marked Done)

## ✅ DONE

> Full history: 905+ pts across 88 issues (C8 alone). See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
- ✅ Gap #5 CP API Prometheus scraping — PRs #788, #793, #799
  - ServiceMonitor (Helm), fix generate_latest(REGISTRY), NetworkPolicies port 8000
  - Prometheus targets: 2/2 health: up ✅
- ✅ CAB-1391 [MEGA] Migration Guide Expansion (13 pts) — stoa-docs PR #68 (Layer7 guide + hub), stoa-web PR #10 (llms.txt)
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
- docs.gostoa.dev = 38 articles, 0 "Coming Soon"
- ADR numbering: stoa-docs owns numbers (001-048). Next: **ADR-049**
- Velocity C8: 905 pts / 88 issues / 129 pts/day (final)
- Velocity C7: 505 pts / 44 issues / 72 pts/day
- Rolling avg: 107.5 pts/day (C7+C8)
- Portal MCP pages: MOCK_SERVERS removed (PR #771) — pages now use real API only
