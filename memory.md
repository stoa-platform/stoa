# STOA Memory

> Derniere MAJ: 2026-02-22 (AI Factory Slack Bot threading — PR #775 merged)

## ✅ DONE

> Full history: 905+ pts across 88 issues (C8 alone). See Linear for complete audit trail.
> Key milestones: Docs v1.0 (107 pts), Rust Gateway (50 pts), ArgoCD+AWX (34 pts), UAC (34 pts)

### Cycle 9 (Feb 22+)
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

CAB-86: TTL Extension — Self-Service (5 pts)

## 📋 NEXT

CAB-1398: [MEGA] AI Factory Slack Upgrade + Dispatch Gap Fixes (26 pts, P2)
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
