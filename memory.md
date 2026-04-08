# STOA Memory

> Derniere MAJ: 2026-04-03 (CAB-1953 gateway ui_url)

## ✅ DONE

> Full history: 2500+ pts across 160+ issues. See Linear for complete audit trail.

### Cycle 14 (Mar 30+)
- ✅ CAB-1953: feat(api,ui) add ui_url to GatewayInstance — PR #2149 (2026-04-03)
  - Migration 088: `ui_url` (String 500, nullable) on `gateway_instances`
  - Self-register persists `ui_url` in all 4 code paths
  - Console: UI + Runtime URL links on /gateways for sidecar/connect modes
  - Council: 8.50/10 Go. 7 files, ~97 LOC
- ✅ fix(api): duplicate personal tenant cleanup (2026-04-02)
  - Root cause: original tenants (12/03) stored email as `owner_user_id`, fix (24/03) stored UUID → index didn't detect duplicates
  - Fix: archived 8 doublons (`free-*-{hex}`), updated 8 originals (`owner_user_id` email→UUID)
  - Migration 051 + `ix_tenants_personal_owner_unique` index confirmed active in prod
  - Data preserved: free-aech (10 APIs, 1 sub, 22 chats), free-i-r0k (1 chat), free-torpedo (2 chats)
- ✅ CAB-1938: fix(api) slug api_id + name-version uniqueness — PRs #2106, #2109, #2111
  - Migration 084: partial unique indexes on (tenant_id, api_name, version) WHERE deleted_at IS NULL
  - Slug generation: `_slugify()` auto-generates URL-safe api_id from name
  - 22 regression tests (slugify, endpoint slug generation, 409 message, soft-delete, versions)
- ✅ CAB-1936: [MEGA] STC + Security Plugins (21 pts) — Council 6.00/10
  - Phase 1: ADR-058 + federation benchmark — PR #2107
  - Phase 2: STC compression plugin + SDK body extension — PR #2108
  - Phase 3: PII filter + secrets detection plugins — PR #2110 (squashed into #2108)
  - 6 builtin plugins total, 2142 gateway tests green, IBAN added to PiiScanner

### Cycle 12 (Mar 3+)
- ✅ CAB-1930: [MEGA] Deploy Single Path — SSE replaces SyncEngine (34 pts) — ADR-059, Council 8.00/10
  - CAB-1931 [api] SSE endpoint + DEPLOY_MODE flag (13 pts) — PR #2072
  - CAB-1932 [go] stoa-connect SSE client + reconnect (8 pts) — PR #2073
  - CAB-1933 [api] Phantom instance cleanup + Alembic 083 (5 pts) — PR #2074
  - CAB-1934 [e2e] Deploy single path verification script (5 pts) — PR #2075
  - ADR-059 published in stoa-docs
- ✅ fix(ui): API backend port 80 → 8000 in k8s deployment — PR #2077
  - Root cause: Helm chart (stoa-infra) had port 8000 since Jan 2026, UI manifest never updated
- ✅ fix(api): bridge git_provider DI with legacy test patches — PR #2076
  - Reduces pre-existing test failures from 102 to ~42 on main
- ✅ Vault credential resolver for gateway adapters — PR #1964
  - `VaultClient.read_secret()`, `credential_resolver.py`, 9 call sites updated, 12 new tests
- 🔴 CAB-1733: [MEGA] FAPI 2.0 + API Fabric + Gouvernance Agentique (34 pts) — Council 8.13/10
  - Spike DONE, ADR-056 DONE, KC 26.5.3 sufficient. Decomposed: 5 subs (CAB-1739-1743)
- ✅ fix(gateway): audit remediations — Council 8.75/10, PR #1633
  - SSE panic fix (HIGH), parking_lot migration (MEDIUM), mode Option accessors (MEDIUM), dep docs (SECURITY), README sync (DX)
- ✅ CAB-1766: Operations Grafana embed + RBAC (13 pts) — Council 8.50/10, PR #1632
- ✅ Arena L1: Remove Kong & Gravitee (score near-zero) — PR #1620
- ✅ docs: Simplify banking terminology across repos — PRs #1622, stoa-docs #111, stoa-web #22
- ✅ fix(audit): Word boundary matching for blocklist false positive — stoa-docs #111
- ✅ docs: Update gateway-arena.md rule for L1 changes — PR #1621
- ✅ CAB-1543: [MEGA] Observability Alert Pipeline (21 pts) — PR #1398
- ✅ CAB-1637: API/MCP Discovery — Smart Connector Catalog (13 pts) — PR #1397
- ✅ CAB-1634: RBAC Taxonomy v2 (21 pts) — PR #1396
- ✅ CAB-1635: OTel Distributed Tracing (21 pts) — PR #1391
- ✅ CAB-1636: [MEGA] HEGEMON Runtime × STOA Gateway Integration (28 pts) — PR #1393
- ✅ CAB-1633: Wire AI Factory through LLM Gateway Proxy (5 pts) — PRs #1336, #1339
- ✅ CAB-1632: Switch repo Private → Public (5 pts) — PRs #1331-#1337
- ✅ CAB-1601: Anthropic Cache Token Tracking (21 pts) — PRs #1292, #1303-#1305
- ✅ CAB-1614: Arena 20 Dimensions — Blue Ocean (21 pts) — PRs #1270, #1276
- ✅ CAB-1552: Lazy MCP Discovery + ADR-051 (5 pts) — PR #1209
- ✅ Queue-Driven AI Factory (8 pts) — PR #1321
- ✅ CAB-1852: Console chat settings UI + X-Chat-Source header (5 pts) — PR #1807
- ✅ CAB-1853: Portal chat settings page + source header (5 pts) — PR #1809
- ✅ CAB-1851: Tenant chat settings API (Phase 1) — PR #1806
- ✅ CAB-1708: Portal eslint/vite upgrade (3 pts) — PR #1561
- ✅ CAB-1707: TokenUsage i18n + persona tests (3 pts) — already on main
- ✅ CAB-1698: Log rotation + model routing (5 pts) — PR #1559

### Historical Cycles (Collapsed)
- **C11** (Feb 27): 152/152 pts, 8 tickets, 9 PRs, 3h wall clock — PRs #1181-#1191
- **C10** (Mar 2-8): 193/193 pts, 13 tickets, 100%
- **C9** (Feb 22+): 830/830 pts, 68 issues, 100%
- **C8** (Feb 16-22): 1305 pts, 88 issues, 186 pts/day
- **C7**: 505 pts, 44 issues, 72 pts/day

## 🔴 IN PROGRESS

CAB-1938: fix(api) upsert conflict clauses with partial indexes — branch `fix/cab-1938-upsert-partial-index`
- PRs #2106, #2109, #2111 merged
- Pending: PR for align upsert conflict clauses (commit 9a7a6eb8 on branch)

CAB-1953 follow-up: gateways stoa-link/stoa-connect doivent envoyer `ui_url` dans leur payload self-register pour que les URLs apparaissent sur /gateways

CAB-802: Dry Run + Script + Video Backup (3 pts) — HUMAN ONLY
- ✅ demo-dry-run.sh: 23/23 PASS
- [ ] Repetitions + video backup (human-only)

CAB-2005: [MEGA] AI Factory v4 — Hardening Post-Leak + Observability (34 pts) — Council 8.50/10
- ✅ Phase 1: Hardening post-leak (11 pts) — PR #2239
  - Hardened `pre-instance-scope.sh` (compound cmd bypass + 50-limit)
  - Stale memory hook, context monitor hook, npm integrity checker, `/memory-consolidate` skill
- [ ] Phase 2: Agent Observability (8 pts) + Spec-Driven pilote (5 pts) + OWASP audit (8 pts)

CAB-1696: [MEGA] AI Factory Audit Remediation (34 pts) — Phase 1 in progress
- [~] CAB-1697: Rules diet Phase 2 (5 pts)
- [ ] CAB-1699: Rust coverage gate (5 pts) — blocked by P1
- [ ] CAB-1700: E2E smoke mock server (5 pts) — blocked by P1
- [ ] CAB-1701: OpenAPI→TS contract testing (3 pts) — blocked by P1

CAB-1795: [MEGA] Unified Secrets Management — HashiCorp Vault (44 pts) — Council 8.25/10
- ✅ CAB-1796 Setup Vault on spare-gra-vps (8 pts) — PR #1710
- ✅ CAB-1797 Migrate Infisical → Vault (5 pts) — PR #1710
- [ ] CAB-1798 ESO → Vault (8 pts) — Phase 2 (blocked: needs Vault live)
- [ ] CAB-1799 Vault Agent VPS (13 pts) — Phase 3 (blocked: needs Vault live)
- [ ] CAB-1801 Rotation extended (5 pts) — Phase 4
- [ ] CAB-1802 SSH + PKI (5 pts) — Phase 5

CAB-1733: [MEGA] FAPI 2.0 (34 pts) — Phase 1+2 done, docs pending
- ✅ CAB-1739 PAR proxy (5 pts) — PR #1526
- ✅ CAB-1741 KC 26.5.3 unify (3 pts) — PR #1526
- ✅ CAB-1742 OTel toggle (3 pts) — PR #1526
- ✅ CAB-1740 private_key_jwt RFC 7523 (8 pts) — PR #1531
- [ ] CAB-1743 FAPI 2.0 docs (5 pts) — ADR-056 drafted, needs stoa-docs PR

## 📋 NEXT

**Human-only**: CAB-1132 Business Model (8), CAB-1126 Video (8), CAB-1125 Punchline (8)
**Deferred**: CAB-1473 WASM (21, 5.00), CAB-1462 ErrorSnap (21, 5.75), CAB-1512 Federation (21, 5.50)

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 17 mars 2026
- Test suite: 5700+ tests, 91% CP-API coverage, 2142 gateway tests
- Arena L0 scores: STOA 83.90 | Gravitee 46.72 | Kong 5.46
- Arena L1 (Enterprise): STOA + agentgateway only (Kong/Gravitee removed PR #1620)
- HEGEMON fleet: 5 Contabo VPS (8vCPU/24GB), Go daemon, Infisical secrets
- ADR numbering: stoa-docs 001-059. Next: **ADR-060**
- docs.gostoa.dev = 41+ articles, 8 migration spokes
