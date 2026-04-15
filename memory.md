# STOA Memory

> Dernière MAJ: 2026-04-15. Archive complète (cycles passés, DONE, etc.) → `memory-archive.md`.

## 🚨 FREEZE ACTIVE (depuis 2026-04-11)

Seul travail autorisé :
- **CAB-2053** stabilisation (voir IN PROGRESS)
- **CAB-2046** remaining subs (CAB-2049/2050/2051 — infra Council S3)
- Hotfixes P0 production

Tous autres MEGA/tickets P1-P3 suspendus jusqu'à CAB-2053 Phase 6 close gate.

## 🔴 IN PROGRESS

### CAB-2053: [MEGA] Feature freeze + CLI-first stabilization (21 pts, P1) — Council 8.0/10
- Phase 0 ✅ feature freeze (PR #2318)
- Phase 1 ✅ In Review queue drained 43→0 (2026-04-12)
- Phase 2 ✅ Bug recurrence root cause — 7 fixes structurels (PRs #2329, #2333, #2335, #2334, #2339, #2336, #2330)
- Phase 3 [owner: —] stoactl completeness: apply/get/delete/list 100% des kinds
- Phase 4 [owner: —] Schema registry unifié `gostoa.dev/v1beta1`
- Phase 5 [owner: —] Context pack CLI-first (cible < 40% context usage)
- Phase 6 [owner: —] Close gate: 7j CI green + feature sans lire `src/` + shadow metric CAB-2051
- Phase 7 [owner: —] ADR-061 controller framework

**Close gate binaire**: feature codée sans lire `src/` — uniquement stoactl + schemas.

### CAB-2054: [MEGA] Council 8 personas (13 pts) — 3/4 phases merged
- Phase 2 🔄 ADR-061 amendment in stoa-docs (PR #151, awaiting review)
- Suite: CAB-2056 (supply_chain S3 axis) — ✅ DONE (commit 6c3f0dc5)

### CAB-2046: [MEGA] Council S3 — Automated Code Review (21 pts)
- CAB-2047 ✅ council-review.sh v0.7.0 (bats tests + doc)
- CAB-2048 ✅ pre-push hook extension (PR #2315)
- CAB-2049 unblocked: council-gate.yml workflow + flag COUNCIL_S3_ENABLED
- CAB-2050 unblocked: council-history.jsonl rotation + gitignore
- CAB-2051 blocked by 2049+2050: Shadow mode 2-3 semaines

### CAB-2065 (courant)
Phase 0 ✅ baseline (PR #2362). Phase 1 pending: Agent Teams flag + canary MEGA.

### Legacy MEGAs en pause (hors freeze)
- CAB-2005 AI Factory v4 — Phase 1 done, Phase 2 backlog
- CAB-1696 AI Factory Audit — Phase 1 in progress (rules diet, coverage gates)
- CAB-1795 Unified Secrets (Vault) — Phase 2-5 blocked par Vault live
- CAB-1733 FAPI 2.0 — docs ADR-056 pending stoa-docs PR

## 📋 NEXT

- **Human-only**: CAB-1132 Business Model, CAB-1126 Video, CAB-1125 Punchline
- **Deferred post-freeze**: CAB-1473 WASM, CAB-1462 ErrorSnap, CAB-1512 Federation

## 🚫 BLOCKED

- **control-plane-api CD**: pods sur `sha-4759aa7` (Apr 9). mypy no-any-return pre-existing bloque docker build. Ticket à créer: `fix(api): resolve pre-existing mypy no-any-return errors`.

## Préférences utilisateur

- MEGA only (21-34 pts sweet spot, 2-4 phases + binary DoD)
- Model: Opus local, Sonnet CI/subagents. Escalade Sonnet>15min → Opus
- Session principale ≠ orchestrateur (tmux pane 0 ORCHESTRE)
- Agent Teams actif (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)

## CI Known Issues

- Dependency Review: GitHub Advanced Security not enabled
- E2E Tests: require running infra, fail on UI-only PRs
- DCO Check: fails on squash-merged commits (expected)
- strict branch protection: `gh api repos/stoa-platform/stoa/pulls/{id}/update-branch -X PUT -f update_method=merge`
- Gateway `cargo test --all-features` requires cmake; `cargo test` local suffit
- cp-api mypy bloque CD (ticket dédié à créer)

## Infra (snapshot)

- **OVH Prod MKS GRA9** 3x B2-15, LB `5.196.236.53`, ArgoCD + KC SSO
- **Contabo HEGEMON** 5x VPS L Nuremberg (w1-w5 backend/frontend/mcp/auth/qa)
- **VPS 3rd-party**: Kong `51.83.45.13`, Gravitee `54.36.209.237`, webMethods `51.255.201.17`
- **Tooling VPS** `51.254.139.205`: n8n, Netbox, Uptime Kuma, Healthchecks
- **Vault** `hcvault.gostoa.dev` (`51.255.193.129`). Infisical legacy `vault.gostoa.dev`
- **Hetzner** ready to decommission. AWS fully decommissioned (Feb 2026)
- Coût: ~€225/mois

## Local Dev

- `.env` repo root (gitignored): KC admin creds
- Tenants console: "oasis", "oasis-gunters". OIDC: `control-plane-ui` (console), `stoa-portal` (portal)
- Memory watchdog: `claude-watchdog` in `~/.local/bin/`
- Parallel: `stoa-parallel` 7-pane tmux. Billing ALL API.

## Clés transversales

- Linear team ID: `624a9948-a160-4e47-aba5-7f9404d23506`
- ADR numbering: stoa-docs owns 001-060. Next = **ADR-061**
- Docs user-facing → stoa-docs. Runbooks/ops-only → stoa/docs/
- stoa-docs branch protection requires Vercel deploy check

## Key Gotchas (détails → `gotchas.md`)

- Dropbox bypass: `git hash-object -w` + `git update-index --cacheinfo`
- Rust `floor_char_boundary` stable ≥1.90 (Use `rust:1.93-bookworm`)
- Axum `.layer()` applies only to routes registered BEFORE it

## L3.5 Autopilot LIVE

- Scan: `claude-autopilot-scan.yml` daily 08:00 UTC weekdays
- Dispatch: `claude-linear-dispatch.yml` via `/go`
- Kill-switches: `DISABLE_L3_LINEAR`, `DISABLE_AUTOPILOT_SCAN`
