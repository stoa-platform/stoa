# STOA Memory

> Dernière MAJ: 2026-04-22. Archive complète (cycles passés, DONE, etc.) → `memory-archive.md`.

## ✅ FREEZE LEVÉ (2026-04-19)

Feature freeze CAB-2053 (déclaré 2026-04-11, PR #2318) officiellement dissous.

Bilan:
- Phase 0 ✅ freeze declaration (#2318)
- Phase 1 ✅ In Review queue drainée 43→0 (2026-04-12)
- Phase 2 ✅ 7 fixes structurels mergés (2026-04-12)
- Phase 3 🟡 stoactl baseline (#2345, 2026-04-12) — gaps audit 2026-04-19 trackés CAB-2119/2120/2121/2122 (P3 reste In Progress)
- Phase 4 ✅ Schema registry `gostoa.dev/v1beta1` (#2348, 2026-04-12)
- Phase 5 ✅ CLI-first context pack (#2349, 2026-04-12)
- Phase 6 ⏸️ Close gate (7j CI green + feature sans `src/`) — deprioritized post-démo
- Phase 7 ⏸️ ADR-061 controller framework — deprioritized post-démo

Raison dissolution: freeze non appliqué en pratique depuis 2026-04-13 (110 commits `main` depuis déclaration, dont features hors scope CAB-2066/2071/2088/2113 + 7 release trains). Maintenir un freeze en façade diluait la gouvernance. Phase 6-7 replanifiées en C16 post-démo (2026-04-28).

Note gouvernance: CAB-2053 reste **In Progress** — rouvert 2026-04-19 pour rétro-décomposition (verify-mega Gate 0 failure, pas de sub-tickets à la fermeture initiale). Le freeze est dissous; CAB-2053 ne sera clos qu'après terminaison de P3 et live verification.

## 🔴 IN PROGRESS

### CAB-2053: [MEGA] Feature freeze + CLI-first stabilization (21 pts, P1)
Rouvert 2026-04-19 pour rétro-décomposition (verify-mega Gate 0). Sub-tickets: CAB-2125 (P0 Done), CAB-2126 (P1 Done), CAB-2127 (P2 Done), CAB-2128 (P3 **In Progress** — gaps audit), CAB-2129 (P4 Done), CAB-2130 (P5 Done), CAB-2131/CAB-2132 (P6/P7 duplicateOf CAB-2118).

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
- **Demo UAC multi-client 5 etapes**: Decision Gate externe revenu `REFRAME` le 2026-04-21. Reframe applique dans `docs/plans/2026-04-21-demo-multi-client.md`: noyau repeatability-first (`reset`, seed deterministe, isolation tenant/persona, golden path) + contrat de preuve par etape + gouvernance recadree + 3 framings prospect. Le plan reste en `challenged`: interdiction de creer le MEGA, de creer des tickets Linear, ou d'executer le plan tant qu'il n'est pas explicitement passe en `validated`.
  - Delta workshop DSL (2026-04-22): scenario `Paiements` juge banking-first et remplace dans les assets de cadrage par `Customer API / Referentiel Client`. Delta conditionnel note: Acte 3 "meme outil, memes regles..." depend du verdict du fix JWT pour passer de promesse verbale a preuve visuelle. Risque Q&A a preparer: mention "reference en production chez une banque centrale europeenne".
  - Decisions Christophe du 2026-04-22 integrees en passe 3bis: `A` fix JWT audience en parallele (subset CAB-2079, evidence test avant phase 4, reintegration `stoa_*` si valide sinon fallback documente), `B` alignement des assets commerciaux sur la promesse restreinte controle + tracabilite + limites assumees, `C` owner des 3 framings = Christophe ABOULICAM.
  - Second challenge externe (2026-04-22): nouveau `REFRAME`. Manques pointes par le challenger puis integres dans le plan: deux contrats de preuve distincts (`Mode A` avec fix JWT / `Mode B` fallback), gate binaire avant phase 4, matrice prospects ↔ mode avec banque hors cible en `Mode B`. Le plan reste en `challenged`.
  - Troisieme challenge externe (2026-04-22): nouveau `REFRAME`, beaucoup plus etroit. Verrou restant integre dans le plan: fiche de qualification pre-demo opposable pour autoriser/interdire `Mode B` et verrouiller les claims par rendez-vous. Le plan reste en `challenged` tant qu'un challenger externe ne confirme pas ce dernier verrou.

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
- **VPS 3rd-party**: Kong, Gravitee, webMethods (IPs → Infisical `infra/vps/*`)
- **Tooling VPS**: n8n, Netbox, Uptime Kuma, Healthchecks (IP → Infisical)
- **Vault** `hcvault.gostoa.dev` (spare-gra-vps). Infisical legacy `vault.gostoa.dev`
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
- Runtime catalog still reads GitLab in prod: deployed source is `stoa-infra/charts/control-plane-api/values.yaml`, not `stoa/control-plane-api/k8s/configmap.yaml` in the monorepo. The monorepo configmap currently says GitHub but is dead code until infra values are migrated
- CAB-2135 scope remains real but the immediate issue is config drift: monorepo `stoa/stoa-catalog/**/uac.yaml`, runtime GitLab catalog, and runtime contract/UAC are three distinct shapes; repo/source convergence is not yet deployed
- GitHub migration requires infra change + secret change: set `GIT_PROVIDER=github` in `stoa-infra`, add `GITHUB_ORG/GITHUB_CATALOG_REPO/GITHUB_GITOPS_REPO`, inject `GITHUB_TOKEN`, then re-run catalog sync and verify `git_commit_sha` comes from GitHub

## L3.5 Autopilot LIVE

- Scan: `claude-autopilot-scan.yml` daily 08:00 UTC weekdays
- Dispatch: `claude-linear-dispatch.yml` via `/go`
- Kill-switches: `DISABLE_L3_LINEAR`, `DISABLE_AUTOPILOT_SCAN`
