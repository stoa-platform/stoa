# STOA Memory

> Derniere MAJ: 2026-04-11 (CAB-2048 DONE — Council S3 pre-push hook extension merged)

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

CAB-2046: [MEGA] Council Stage 3 — Automated Code Review (21 pts) — Council S1 8.125/10, S2 8.5/10 Go
- Decomposed into 5 sub-issues (CAB-2047 through CAB-2051), 3-phase DAG
- CAB-2047 (13 pts): council-review.sh — Steps 1+2a+2b+3a+3b+3c+4+5 ALL DONE. **Ready to unblock CAB-2048/49/50/51.**
  - ✅ Step 1: skeleton + Étape 0 pre-checks (deps, gitleaks pre-flight, portable stat, numstat, truncation 10k) — PR #2303, commit `e98e88c0`, 333 LOC
  - ✅ Step 2a: cost guardrails (COUNCIL_DISABLE kill-switch, COUNCIL_DAILY_CAP_EUR default €5, SHA dedup) — PR #2304, commit `fd8c7d66`, +134/-5 → 462 LOC
  - ✅ Step 2b: anthropic_call() + evaluate_axis(conformance) + MOCK_API fixtures — PR #2306, commit `9fb4a235`
  - ✅ Step 3a: prompts externalisés → `scripts/council-prompts/{conformance,debt,attack_surface,contract_impact}.md`, `load_prompt(axis)` loader, v0.4.0 — PR #2307, merge `c7108607`, +152/-41. Only conformance invoked in main() — other 3 axes are content-only until Step 3c.
  - ✅ Step 3b: `fetch_linear_ticket` (GraphQL issueSearch → TICKET_CONTEXT) + `fetch_db_context` (sqlite3 -readonly, match repo_path, cross-component contracts → DB_CONTEXT) + `evaluate_axis` 4th arg `extra_context` wrapped in `<context>…</context>`/`<diff>…</diff>`. v0.5.0 — PR #2308, merge `423641f7`, +263/-7 → 949 LOC.
  - ✅ Step 3c: parallel 4-axis orchestration + aggregate_scores + council-history.jsonl. Incremental PID capture (Adj #1), `aggregate_scores <tmpdir> <failed> <expected_count>` pure function (exit 0/1/2), missing-file-for-expected-axis counts as error (closes silent-skip gap), `sum_usage_tokens`/`compute_cost_eur`/`write_history`, `now_ms()` portable ms timer (BSD date %3N fallback), 3 missing MOCK_API fixtures (debt, attack_surface, contract_impact), `.gitignore` entries. v0.6.0 — PR #2310, merge `ed56cf82`, +375/-27 → 1278 LOC. Tested 4 scenarios with MOCK_API=1: APPROVED rc=0, REWORK rc=1, ERROR rc=2, 3-axis rc=0. Shellcheck clean.
  - ✅ Step 4: bats test suite (15 tests, 5 DoD scenarios + 3 edge + 3 token + 4 cost) + `.claude/rules/council-s3.md` (scoped, ~11.6K) + SKILL.md S3 cross-ref + source guard on `main "$@"`. v0.7.0 — PR #2312, merge `ad168f48`, +553/-2. bats-core 1.13.0 local, shellcheck clean, all 4 required CI checks green (non-required SAST JS ESLint failure pre-existing in control-plane-ui unrelated).
  - ✅ Step 5: real API validation against 2 live diffs, 2026-04-11. Key='stoa/shared/anthropic' (Vault). No prompt tuning needed — feedback quality was accurate and non-hallucinated on first try.
    - **Run 1** (sanity, docs-only): 02c4ff63 memory.md 48 LOC → APPROVED 10.00/10, 5000ms parallel, 17456 in / 561 out = 18017 tokens, **€0.0559**. All 4 axes 10/10. `diff_sha=8a0156481d9a`.
    - **Run 2** (real code+tests): ad168f48 Step 4 bats+doc 555 LOC → APPROVED 9.50/10, 7000ms, ~41986 tokens, **€0.1241**. Scores: conformance 10, debt 9, attack_surface 9, contract_impact 10. `diff_sha=5e4d2901433a`.
    - **Run 2 (re-run FORCE_DEDUP=0)**: APPROVED 9.25/10, 7000ms, €0.1236. Scores stable ±0.25 across runs (conformance 9 vs 10 drift only).
    - **Per-axis feedback quality**: all 4 axes produced accurate, technically grounded feedback (noted kebab-case / snake_case / source guard / test counts 9+3+4 / pure helpers <50 lines / zero contract impact). Zero hallucinated blockers across both runs.
    - **SHA dedup verified**: 3rd ad168f48 invocation without FORCE_DEDUP exited 0 with "Diff SHA 5e4d2901 already evaluated today ... SKIP" — no API call, correct replay.
    - **Cost ledger verified**: daily cap tracker cumulative €0.304 / €5 after 3 runs — accurate.
    - **Total Step 5 spend**: €0.3037 (3 runs, well under €5 cap).
    - Handoff artifacts: `council-history.jsonl` has 3 entries (all APPROVED, schemas pass `jq .` cleanly). Preserved tempdir output lives in `/tmp/council.*` — safe to discard.
- ✅ CAB-2048 (2 pts): pre-push hook extension — **DONE** 2026-04-11, PR #2315 (merge `81aaeda3`), +29 LOC
  - `.claude/hooks/pre-push-quality-gate.sh` extended with Council S3 block after existing lint/format/tsc/axe checks
  - Threshold: `COUNCIL_MIN_DIFF_LINES` (default 20) — small diffs go through CI-only (council-gate.yml CAB-2049)
  - Kill-switch: `DISABLE_COUNCIL_GATE=1` → BYPASSED, logs JSONL entry `{"status":"BYPASSED","reason":"local_kill_switch","diff_lines":N}`
  - Graceful fallback: missing/non-executable `scripts/council-review.sh` → SKIPPED (exit 0), hook stays resilient to partial checkouts
  - Reuses existing `MERGE_BASE` + `REPO_ROOT` + `COUNCIL_HISTORY_FILE` env convention (matches `council-review.sh` default `${REPO_ROOT}/council-history.jsonl`)
  - **Manual test plan (all 4 branches verified with a 30-line probe commit at `scripts/_probe.txt`)**:
    1. BYPASSED: `DISABLE_COUNCIL_GATE=1` → exit 0, JSONL entry written
    2. Threshold SKIPPED: `COUNCIL_MIN_DIFF_LINES=9999` → exit 0, no API call
    3. Missing-script fallback: `mv scripts/council-review.sh ...bak` → exit 0, clear SKIPPED log
    4. Council invoked: diff ≥ 20 → `council-review.sh --diff MERGE_BASE..HEAD` runs, exits 2 on REWORK/error and prints `DISABLE_COUNCIL_GATE=1` bypass hint
  - **Probe trick for future hook testing**: create file outside all component dirs (e.g. `scripts/_probe.txt`) so the `ONLY_DOCS=false` + no-`HAS_*-flags` path runs Council without triggering the ruff/ESLint/clippy checks that use the whole-dir globs
  - No regression on existing checks (classification + run_check blocks untouched). shellcheck clean on new code (pre-existing SC2294 on `eval` unchanged)
  - CI: 3 required checks ✅ (License, SBOM, Signed Commits) + Regression Test Guard ✅. Non-required `SAST JS ESLint (control-plane-ui)` pre-existing failure on `src/test/i18n-keys.test.ts:35` (`security/detect-unsafe-regex`) — unrelated to this PR, needs its own fix ticket
- CAB-2049 (3 pts): council-gate.yml CI workflow + feature flag vars.COUNCIL_S3_ENABLED — **UNBLOCKED** (parallel with CAB-2048)
- CAB-2050 (1 pt): council-history.jsonl rotation + gitignore — **UNBLOCKED** (parallel with CAB-2048)
- CAB-2051 (2 pts): Shadow mode observation 2-3 weeks — now blocked only by 2049 + 2050
- Claim file: `.claude/claims/CAB-2046.json` — Phase 1 released for handoff (owner=null)
- Cost guardrails active on main: €5/day hard cap, SHA dedup, COUNCIL_DISABLE kill-switch
- Audit base: `audit-results.md` (root) — pre-implementation audit of existing Council infra
- **Next session handoff (Step 4 — bats tests + documentation)**:
  - Start from `scripts/council-review.sh` v0.6.0 on main (`ed56cf82`, 1278 LOC)
  - Implement `tests/bats/council-review.bats` with 5 scenarios on `aggregate_scores` (per CAB-2047 DoD Adj #9):
    1. 4 axes all ok, avg >= 8.0 → APPROVED exit 0
    2. 4 axes all ok, avg < 8.0 → REWORK exit 1
    3. 3 axes ok + 1 error → averaged over 3, status consistent
    4. 2 axes error → exit 2 technical failure
    5. contract_impact skipped (db stale, expected_count=3) → avg over 3 axes, db_fresh=false
  - Bats approach: `source scripts/council-review.sh` is problematic (runs main). Instead, extract testable helpers or use a guard: add `[[ "${BASH_SOURCE[0]}" == "${0}" ]] && main "$@"` at bottom so `source` doesn't execute main. Then bats can directly call `aggregate_scores`, `sum_usage_tokens`, `compute_cost_eur` against fabricated fixtures in per-test tmpdirs.
  - Install bats via `brew install bats-core` (local) or add to CI via apt/npm. Add a `tests/bats/` README pointing to `bats tests/bats/council-review.bats`.
  - Write `.claude/rules/council-s3.md`: overview, 3 exit codes, env vars (COUNCIL_DISABLE, COUNCIL_DAILY_CAP_EUR, COUNCIL_FORCE_DEDUP, MOCK_API, ANTHROPIC_API_KEY, LINEAR_API_KEY), how the 4 axes score, JSONL schema, troubleshooting (gitleaks block, daily cap reached, SHA dedup hit), FAQ (cost, privacy).
  - Update `.claude/skills/council/SKILL.md` to reference S3 as the post-code-change gate (S1=ticket pertinence, S2=plan validation, S3=code review via `scripts/council-review.sh`).
  - Target PR size: <250 LOC (tests + doc only, no script logic changes)
- **Step 5 (after Step 4)**: real API validation
  - Requires `ANTHROPIC_API_KEY` in env and a small real-diff target (pick a recent docs-only PR for low cost)
  - Expected first-run cost: €0.04-0.06 for a ~100-line diff across 4 axes
  - Observations to capture: per-axis latency, usage.input_tokens/output_tokens realism, prompt quality (any hallucinated blockers?), daily cap accuracy
  - If any axis drifts (score consistently off), tune `scripts/council-prompts/<axis>.md` iteratively — prompts are externalized per Step 3a
- **Session log**: Step 5 completed 2026-04-11. Real API validation against 2 live diffs (48 LOC + 555 LOC), 3 total runs, €0.304 spend. Per-axis feedback accurate, no hallucinated blockers, no prompt tuning needed. SHA dedup + daily cap confirmed. CAB-2047 fully green — Phase 2 (CAB-2048/49/50) unblocked.

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
