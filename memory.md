# STOA Memory

> Dernière MAJ: 2026-05-12. Archive complète (cycles passés, DONE, etc.) → `memory-archive.md`.

## Session Notes — 2026-05-12

- CAB-2219 Phase 6.5 cp-ui five-state rendering implemented on branch `codex/cab-2219-phase65-cpui-states` in worktree `/Users/torpedo/hlfh-repos/stoa-cab2219-phase65`. Scope stayed cp-ui-only: Guardrails cards now render backend-shipped `by_guardrail[*].state` directly, preserve `null` counts, display `metrics_unavailable` / `no_evaluations` / `evaluations_zero_trips` / `trips_observed` / `stale_data` wording, add Phase 6.4 response types, unskip CAB-2214 cp-ui red tests, and add AR-1 anti-regression coverage for Security Posture vs Security & Guardrails subtitles. Validation passed: targeted vitest (33 passed), full `npm run test` (2338 passed, 11 skipped), `npm run lint` (0 errors, 49 pre-existing warnings), `npm run format:check`, `npm run build`, `git diff --check`. Browser observation on local Vite route redirected to `/login` as expected without auth, so visual page inspection was auth-gated.

## Session Notes — 2026-05-11

- CAB-2218 Phase 6.4 cp-api reader implemented on branch `codex/cab-2218-phase64-cpapi-reader`. Scope cp-api-only: `/v1/admin/gateways/metrics` reads new guardrails counters + keeps legacy, derives A15 5-state precedence server-side, emits A4 4-field timestamps, applies A5 capped freshness (60min ceiling), separates A16 trips/error counts, ships A17 per-guardrail health, and bounds E6 `stale_reason` enum. Validation: targeted pytest (37 passed, 4 later-phase skips), ruff/black/mypy clean, coverage 77.25%. Pre-existing OpenAPI snapshot debt on `AuditEntry.is_synthetic` from Phase 2 obs data visibility batch addressed in companion commit.
- CAB-2217 Phase 6.3 implemented on `feat/cab-2213-phase63-nonmcp-observe`: gateway non-MCP observe-only guardrail counters for bounded JSON `api_proxy`/`dynamic_proxy`, skipped-body no-counter semantics, explicit `ws_proxy` defer decision, and A10 anchors updated.
- CAB-2214 Phase 6.0 prep started under master ticket CAB-2213 on branch `feat/cab-2213-phase60-docs-redtests` in worktree `/Users/torpedo/hlfh-repos/stoa-cab2213-phase60`, based on validated `origin/codex/phase6-guardrails-full` (`1d0284dbc`). Scope is docs/cardinality + SPEC + red-test scaffolding only; no gateway producer, cp-api reader, UI behavior, rollout, or smoke implementation. Claim file: `.claude/claims/phase-6-0-validation.json` with heartbeat protocol.

- CAB-2214 Phase 6.0 red-test proof captured locally: gateway `cargo test spec_ac -- --nocapture` failed 6/6 on missing full guardrails producers/zero-init/skip modeling; cp-api `python3 -m pytest tests/test_spec_cab_2214_phase60.py -q` failed 10/10 on missing semantic API fields/readers/docs artifacts; cp-ui `npm run test -- --run src/__tests__/spec/cab-2214-phase60.test.ts` failed 2/2 because current `guardrailCardState` derives `no-sample` instead of rendering backend `evaluations_zero_trips` / `trips_observed`. This is expected for Phase 6.0 red scaffolding.

- CAB-2214 Claude §11 review returned `blocked` on operational gates: unskipped red tests, missing Council archive, and LOC budget. F1/F2 addressed inline: all 18 red tests are now skipped with TODO Phase reasons, and Council archive exists at `docs/audits/2026-05-11-cab-2213-council/findings.md`. F3 LOC strategy remains operator decision (stack merge vs micro-PR split vs explicit exception).

- CAB-2215 Phase 6.1 gateway metric contract implemented on branch `feat/cab-2215-phase61-gateway-metrics` in worktree `/Users/torpedo/hlfh-repos/stoa-cab2215-phase61`, stacked on CAB-2214 / CAB-2213 Phase 6.0. Scope stayed gateway metrics only: `stoa_guardrails_evaluations_total` and `stoa_guardrails_decisions_total` use bounded labels, zero-initialize A10 in-scope series (20 evaluation + 80 decision), reject forbidden decision labels such as `rate_limited`, and leave MCP/non-MCP call-site instrumentation to Phase 6.2/6.3. Validation: `cargo fmt --check`, `cargo test spec_ac -- --nocapture --test-threads=1`, `cargo test test_metrics_no_auth_required -- --nocapture --test-threads=1`, and full `cargo test` passed in `stoa-gateway`.

- CAB-2216 Phase 6.2 MCP coverage implemented on branch `feat/cab-2216-phase62-mcp-coverage` in worktree `/Users/torpedo/hlfh-repos/.worktrees/stoa-cab2216-phase62`, based on merged Phase 6.1. MCP tool-call guardrails now emit full bounded evaluation/decision counters for allow, redact, block, error taxonomy, including rate-limit as `decision="block"` and disabled-policy no-delta coverage, while preserving legacy trip counters. Validation passed: `cargo fmt --check`, targeted `cargo test spec_ac2`, targeted integration `guardrails_metrics::mcp_guardrail_metrics_cover_phase62_contract`, full gateway integration, full `cargo test`, `cargo clippy --all-targets -- -D warnings`, and `git diff --check`.

- Phase 6 Guardrails non-MCP + 4B-full opened on branch `codex/phase6-guardrails-full` in worktree `/Users/torpedo/hlfh-repos/stoa-phase6-guardrails-full`. Output plan: `docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md` with `validation_status: draft`, `triggers: [a, b]`. No code implementation started: Phase 6 is a separate MEGA and must pass external non-Claude challenge plus Council if HIGH impact before any gateway/API/UI changes. The draft narrows the new counter labels to bounded dimensions (`deployment_mode`, `surface`, `guardrail`, `decision`) and explicitly rejects tenant/route/policy/tool/raw-path labels in the first implementation slice unless challenged and amended.

- Observability Data Visibility Phase 0.5c Data Prepper load tuning executed as read-only prod diagnostic on branch `codex/phase05c-dp-load-tuning` in worktree `/Users/torpedo/hlfh-repos/stoa-phase05c-dp-load-tuning`. Output file: `docs/audits/2026-05-11-data-prepper-load-tuning/findings.md`. Verdict `monitor_only`: no infra tuning patch needed now. OVH prod Data Prepper showed 0 Data Prepper/Alloy dataprepper error lines across 12h/6h/2h/30m windows, buffer drained `206 -> 0` in 60s, OpenSearch successful docs increased `2081098 -> 2083155`, bulk retries/server errors stayed 0, and fresh probe trace `453484aa194a174879dff61c6f99f8a8` was visible in OpenSearch with 5 spans within a measured upper bound of 71s. Reopen only if trace indexing lag >30min, buffer remains non-zero across samples, or sink/error counters start increasing.

## Session Notes — 2026-05-07

- Observability plan post-activation update prepared on branch `docs/observability-plan-update-post-activation-draft` in worktree `/Users/torpedo/hlfh-repos/stoa-observability-plan-update-post-activation-draft`. Scope docs-only: updated `docs/plans/2026-05-07-observability-data-integrity.md` after #2724/#2726/#2727/#2730/#2733/#2734 and stoa-infra #73/#75. Important verified divergence from prompt: stoa-infra #75 was no longer DRAFT/HOLD; GitHub showed it merged 2026-05-08 07:40:34 UTC, and read-only OVH prod check showed `ENABLE_AUDIT_TRAIL_CONSUMER="true"` with `audit-trail-pg-consumer` Stable/MEMBERS=1/TOTAL-LAG=0. Plan now keeps PR-1B blocked on PR-1A6 post-activation evidence amend, not on #75 merge itself. Annex A/B and AR decisions were not changed.

- PR-1A5 Audit consumer runtime verification evidence produced on branch `docs/audit-consumer-runtime-verification` in worktree `/Users/torpedo/hlfh-repos/stoa-audit-consumer-runtime-verification`. Output file: `docs/audits/2026-05-09-audit-consumer-verification/findings.md`. OVH prod was verified with `KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh`; deployed image was `ghcr.io/stoa-platform/control-plane-api:dev-6400f51a51b32e4f3fb9d2b8010a90dc9d2ae8cc` (#2726). A non-chat `GET /v1/tenants/demo/export` event at `2026-05-07T19:24:38Z` produced Kafka event `b9ca45fb-67b3-4823-98af-c198c3d68871`, advanced `audit-trail-pg-consumer` offset `30018→30019` with lag `0`, persisted to `audit_events`, and was visible via `/v1/audit/demo`. Caveat: during collection the deployment rolled to revision 515 with `ENABLE_AUDIT_TRAIL_CONSUMER=false`; current group state is `Empty`/`MEMBERS=0`, so #2726 persistence is proven when enabled but continuous prod ingestion is currently disabled.

- PR-2 Live Calls http_route migration implemented on branch `fix/live-calls-http-route-metric-integrity` in worktree `/Users/torpedo/hlfh-repos/stoa-live-calls-pr2`. Scope stayed frontend-only: Live Calls PromQL request queries now share `MODE_FILTER`, route-level panels group by `http_route`, `groupByLabel` uses explicit `(unlabelled)` fallback, Top Routes filters unusable route labels and renders a route-label unavailable state, synthetic heatmap generation was removed in favor of an explicit not-wired state, Active Modes counts jobs, scope-mismatch banner added, and traces empty-state now distinguishes Prometheus metrics from Tempo/OpenSearch traces. No AuditLog, Guardrails, backend, gateway Rust, Tempo/Loki/OpenSearch, sidebar/nav, or real heatmap implementation changes. Validation passed: `npm run test -- --run` (2302 passed, 11 skipped), targeted CallFlow/usePrometheus regressions (54 passed), `npm run lint` (50 pre-existing warnings, 0 errors), `npm run format:check`, `npm run build` after `shared/npm ci`, `git diff --check`, and static scan confirmed no Live Calls `sum by (path)`, `count by (path)`, `metric.path`, old `unknown` fallback, or synthetic heatmap hash block remains.

## Session Notes — 2026-05-09

- PR-4 observability nav IA cleanup on `chore/observability-nav-ia-cleanup`: removed advertised legacy Gateway sidebar links to `/gateway-security` and `/gateway-guardrails` while preserving `App.tsx` deep-link redirects to `/observability/security`; aligned Security Posture subtitle with validated AR-1 wording and added sidebar/title regression coverage. Frontend validation passed (`lint`, `format:check`, regression vitest, full vitest, build, `git diff --check`).

## Session Notes — 2026-05-04

- Hotfix gateway discovery count: `stoa-gateway` no longer falls back to the global API catalog when scoped `gateway_id` discovery returns empty, and skips catalog discovery until auto-registration has a gateway ID. Console labels the edge-MCP heartbeat count as "MCP Tools" instead of "Discovered APIs" because it comes from `tool_registry`. This prevents gateway details from implying global tools/APIs (e.g. 51) are deployed APIs when routes are zero. Regression coverage added for coarse/per-operation discovery and the UI label.

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
  - Delta workshop DSL (2026-04-22): scenario `Paiements` juge banking-first et remplace dans les assets de cadrage par `Customer API / Referentiel Client`. Delta conditionnel note: Acte 3 "meme outil, memes regles..." depend du verdict du fix JWT pour passer de promesse verbale a preuve visuelle. Risque Q&A a preparer: mention "reference en production chez un acteur europeen fortement regule".
  - Decisions Christophe du 2026-04-22 integrees en passe 3bis: `A` fix JWT audience en parallele (subset CAB-2079, evidence test avant phase 4, reintegration `stoa_*` si valide sinon fallback documente), `B` alignement des assets commerciaux sur la promesse restreinte controle + tracabilite + limites assumees, `C` owner des 3 framings = Christophe ABOULICAM.
  - Second challenge externe (2026-04-22): nouveau `REFRAME`. Manques pointes par le challenger puis integres dans le plan: deux contrats de preuve distincts (`Mode A` avec fix JWT / `Mode B` fallback), gate binaire avant phase 4, matrice prospects ↔ mode avec banque hors cible en `Mode B`. Le plan reste en `challenged`.
  - Troisieme challenge externe (2026-04-22): nouveau `REFRAME`, beaucoup plus etroit. Verrou restant integre dans le plan: fiche de qualification pre-demo opposable pour autoriser/interdire `Mode B` et verrouiller les claims par rendez-vous. Le plan reste en `challenged` tant qu'un challenger externe ne confirme pas ce dernier verrou.
  - Dernier verrou gouvernance ajoute ensuite: toute exception `Mode B` exige un sign-off explicite, nominatif et horodate de Christophe ABOULICAM avant la demo. Sans ce sign-off, `Mode B` est interdit.

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
- ADR numbering: stoa-docs owns the ADR index; check `stoa-docs/docs/architecture/adr/` before creating a new ADR.
- Docs user-facing → stoa-docs. Runbooks/ops-only → stoa/docs/
- ADR-067 doctrine added to agent context (2026-04-25): `UAC describes. MCP projects. Smoke proves.` V1 `endpoint.llm` metadata is warning/recommended for MCP-exposed operations; malformed metadata is an error when present; V2 target = mandatory for new MCP endpoints. Local references: `CLAUDE.md`, `AGENTS.md`, `.claude/docs/uac-llm-ready.md`.
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
