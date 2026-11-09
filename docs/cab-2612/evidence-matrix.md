# CAB-2612 — Evidence matrix (09/11 recovery lock)

Read-only GitHub state gathered on 2026-11-09 (last PR check refresh 20:58 UTC).
Sources are `gh run view`, `gh run download`, and `gh pr view`. No workflow was
re-run. No secret value is copied. A green job, a merged PR, or a closed
ticket is not a PASS.

Statuses: **PASS réel**, **FAIL**, **SKIP**, **NON VÉRIFIÉ**, **à décider par Christophe**.
**PASS réel** means the named check executed and met its own assertion.
It does not mean the milestone journey or production is accepted.
Technical owner: unassigned. Final calls: Christophe.

Base inspected: `stoa` `main` `9199b3442fb8ffdb387c5cfc0934e88e867afe0f`.

## A. Criterion 2 — demo smoke run 42556138847

| Field | Value |
|---|---|
| URL | https://github.com/stoa-platform/stoa/actions/runs/42556138847 |
| Workflow | Demo Smoke Observation, event `schedule` |
| Commit | `c4b1ea7bc801b0f6858f1e043ac3c710deae88fb` on `main` |
| Created | 2026-11-09T03:23:29Z |
| Job | Demo Smoke (observation) `128962148470`, conclusion `success`, completed 2026-11-09T03:30:45Z |
| Environment | GitHub-hosted `ubuntu-latest`, Docker Compose profile `demo` on localhost. Not production. |
| Artifact | `demo-smoke-42556138847-1` (id `13647706305`, 1796 bytes, SHA256 `0451c9f137a9cb9d908066b3eb053d4646b0391e372a8169a70a92af42ced7df`) |

The script on that commit scores only AT-0..AT-5 (`scripts/demo-smoke-test.sh`,
`AT_FILTER` default `1,2,3,4,5`). AT-5b and AT-LLM are notes. They do not
change `Score:`.

Job log (`gh run view 42556138847 --log`):

- Line 51, and again line 3088: `STOA_DISABLE_AUTH: true`.
- Line 3087: `DEMO_SMOKE_BLOCKING: false`. A failing smoke would not fail the job.
- Lines 3035 and 3043: command `./scripts/demo-smoke-test.sh --no-observability-ui`.
- Line 3225: gateway log `ToolProxyClient initialized WITHOUT OIDC — using unauthenticated endpoints`.
- Lines 3378, 3386, 3410, 3414: control plane `Demo/dev auth bypass accepted`, `user_id=demo-dev-bypass`, `environment=dev`.
- No `::notice::Demo smoke is observation-only` line, which the workflow prints only when the script exit is non-zero. The script exit for this run is therefore 0.

Artifact `demo-smoke.log` (same text in `demo-smoke-tail.log`):

| Lines | Text | Class |
|---|---|---|
| 1 | `WARN — smoke not UAC-driven` | Legacy fallback, not a scored step |
| 3–17 | Section headers AT-0, AT-1, AT-2, AT-3, AT-4, AT-5, AT-5b, AT-LLM | Steps the script entered |
| 29 | `[PASS] AT-0 cp-api+gateway+mock reachable` | **PASS réel** (local). Authentication inactive |
| 30 | `[PASS] AT-1 API_ID=demo-api-smoke` | **PASS réel** (local). Authentication inactive |
| 31 | `[PASS] AT-2 DEPLOYMENT_ID=…, route synced in ~0s` | **PASS réel** (local). Authentication inactive |
| 32 | `[PASS] AT-3 SUBSCRIPTION_ID=…, API_KEY acquired` | **PASS réel** (local). Key value not in the artifact. Authentication inactive |
| 33 | `[PASS] AT-4 GET /apis/demo-api-smoke/get HTTP 200, request_id=n/a` | **PASS réel** of HTTP 200 on the legacy path. `request_id` absent. CP authentication inactive. Job log line 3439 shows gateway span `auth_type=api_key` for that proxy hop only |
| 34 | `[PASS] AT-5 counter=proxy_requests_total, value=1, log=no-log-check` | Counter **PASS réel** (local). Log correlation **NON VÉRIFIÉ** (`no-log-check`, because `request_id=n/a`) |
| 36 | `smoke not UAC-driven; using legacy fallback DEMO_API_NAME=demo-api-smoke, path=/get` | UAC path **NON VÉRIFIÉ** |
| 37 | `AT-5b skipped (OBS_VISIBILITY_CHECK=off)` | **SKIP** |
| 38 | `AT-LLM skipped (no DEMO_UAC_CONTRACT)` | **SKIP** |
| 40–41 | `Score: 6/6` / `Verdict: REAL_PASS — DEMO READY` | Script label for the six local checks above. Not a milestone acceptance |

Authentication for this run: **inactive** (`STOA_DISABLE_AUTH=true`, demo bypass, gateway tool proxy without OIDC). Not a failed login.

## B. Gap matrix

| Écart | Critère | Périmètre | Responsable | Correctif ou décision | PR-commit | Environnement | Run ou artefact | Statut |
|---|---|---|---|---|---|---|---|---|
| Prod MCP smoke step not executed inside a green job. Log line 46: `prod MCP non publiée (DNS retiré le 21/10)`. Steps checkout, SDK install, and `Run MCP SDK smoke against prod` are `skipped` | 1 | `mcp.gostoa.dev` | à attribuer | Do not republish only to get a green light. #3150 classifies SKIP as not a pass; it is open | #3150 head `fd07b214297343d60f247ceae0ba53ffdad3bb6b` (open, not draft). Run commit `c4b1ea7bc801b0f6858f1e043ac3c710deae88fb` | prod probe, GHA | [42583971143](https://github.com/stoa-platform/stoa/actions/runs/42583971143) job `129049204795`, 2026-11-09T08:10:00Z, job `success` | SKIP |
| Keep the public MCP endpoint unpublished, or require a real executed test | 1 | public MCP | Christophe | Explicit applicability decision | same run as above | prod DNS | log line 38–46 of run 42583971143 | à décider par Christophe |
| Critical-control inventory is not on `main` and is not accepted | 1 | CI controls | à attribuer | #3153 adds `docs/ci/controls-truth-inventory.md`. Scanner exits 0 and is not wired to a workflow | #3153 head `0043d90cbcf79eb8193e7dfd46370de42b333614` (open). No failing check at read time | GHA PR checks | PR checks only; no new prod run | NON VÉRIFIÉ |
| Dev deploy stayed green after the endpoint was not healthy (`HTTP 000`) | 1 | gateway, portal, console dev | à attribuer | #3154 records the result and can fail only if `DEV_POST_DEPLOY_REQUIRED=true` (PR default remains green). Not merged | #3154 head `05f15f22cdd0610187fdd95c7db58a320c7f1829` (open). No failing check at 20:58 UTC | dev GitOps | Gateway [42173378271](https://github.com/stoa-platform/stoa/actions/runs/42173378271) log line 11178 (2026-11-06, `1a327342c188`). Portal [42591211264](https://github.com/stoa-platform/stoa/actions/runs/42591211264) log line 3062 (2026-11-09, `303010db9877`). Console [42067952395](https://github.com/stoa-platform/stoa/actions/runs/42067952395) log line 7708 (2026-11-05, `b3b26485db7f`). All three runs `success` | FAIL |
| Dev health smoke did not run: `SKIPPED, no dev target` | 1 | gateway, portal, console | à attribuer | #3154 names the skip. Not merged, so `main` is unchanged | same #3154 | dev | same three runs, smoke-test warnings at log lines 11362, 3246, 7892 | SKIP |
| CP API `smoke-test` job skipped on the main push | 1 | control-plane-api dev | à attribuer | #3154. Not merged | merge of #3138 is `8b7cc89f91797a648071654b0d098d62e6d4401c` | dev | [42591592425](https://github.com/stoa-platform/stoa/actions/runs/42591592425) job `smoke-test` `skipped`, run `success`, 2026-11-09T09:12:22Z | SKIP |
| Truthfulness fixes are not on `main` | 1 | workflows | à attribuer | Merge is a separate decision; this matrix does not merge them | #3150, #3154 open | n/a | PR heads above | NON VÉRIFIÉ |
| AT-0 local reachability | 2 | demo Compose | à attribuer | Not a production journey | `c4b1ea7b` | GHA Compose | artifact line 29 | PASS réel |
| AT-1 declare API, auth bypass | 2 | demo Compose | à attribuer | Authenticated journey still required | `c4b1ea7b` | GHA Compose | artifact line 30; job log line 3378 | PASS réel |
| AT-2 route sync, auth bypass | 2 | demo Compose | à attribuer | Same | `c4b1ea7b` | GHA Compose | artifact line 31; job log line 3386 | PASS réel |
| AT-3 subscription, auth bypass | 2 | demo Compose | à attribuer | Same | `c4b1ea7b` | GHA Compose | artifact line 32; job log line 3410 and 3414 | PASS réel |
| AT-4 HTTP 200 on legacy path, `request_id=n/a` | 2 | demo Compose | à attribuer | UAC path not used | `c4b1ea7b` | GHA Compose | artifact line 33 | PASS réel |
| AT-5 counter `proxy_requests_total=1` | 2 | demo Compose | à attribuer | Log proof is a separate row | `c4b1ea7b` | GHA Compose | artifact line 34 | PASS réel |
| AT-5 log correlation `no-log-check` | 2 | demo Compose | à attribuer | Needs a request id | `c4b1ea7b` | GHA Compose | artifact line 34 | NON VÉRIFIÉ |
| AT-5b observability UI | 2 | Grafana/console/portal | à attribuer | Flag forced off | `c4b1ea7b` | not started | artifact line 37 | SKIP |
| AT-LLM | 2 | UAC `endpoint.llm` | à attribuer | No contract. Exclusion needs an explicit acceptance if it stays out of scope | `c4b1ea7b` | not started | artifact line 38 | SKIP |
| UAC-driven path | 2 | demo contract | à attribuer | Legacy fallback used | `c4b1ea7b` | GHA Compose | artifact lines 1 and 36 | NON VÉRIFIÉ |
| Authentication of run 42556138847 | 2 | CP and gateway OIDC | à attribuer | Left disabled by the workflow | workflow env on `c4b1ea7b` | GHA Compose | job log lines 51 and 3088 | SKIP |
| Milestone journey: auth on, allow and deny, trace, observability | 2 | current milestone | Christophe | Define the target path. Do not count this demo as that path | none | authorized env | none | NON VÉRIFIÉ |
| OpenBao operational close: network path, consumers and rights, TLS, audit, unseal/restart, backup and restore | 3 | CAB-1795 / CAB-2607 | à attribuer | Reuse existing work. Nothing in the readable repos shows those proofs. Do not repeat a Linear claim as evidence | #3134 merged 2026-11-07, merge `0cdc606b132675423bb64749f256f325a50614f0`. Helper `scripts/lib/stoa-secret.sh` defaults to `https://127.0.0.1:18200` | not shown | no run of an authorized restore or unseal | NON VÉRIFIÉ |
| Live VaultClient / OpenBao tests | 3 | control-plane-api CI | à attribuer | `VAULT_IT_ADDR` unset | `8b7cc89f` | GHA | run 42591592425 log line 15870, tests SKIPPED | SKIP |
| Docs say the Infisical init container is gone; `main` still has it | 3 | chart vs stoa-docs | à attribuer | Land #3139 before treating the docs as true, or revert the docs claim | stoa-docs#236 merged 2026-11-09T09:05:51Z, merge `ee458a9dd7c06a4e066963bdfc413d1ab5d0f164`. Its body says merge after #3139. `charts/stoa-platform/templates/_helpers-infisical.tpl` is still on `main` | docs vs `stoa` `main` | file present at `9199b344` | FAIL |
| Chart cut-over to OpenBao monitoring / init-container removal | 3 | `charts/stoa-platform` | à attribuer | #3139 open, helm lint success, not deployed | head `ed0efbccfe15125d1ba1681e94ae7eef426d9ecf` | CI helm only | PR checks, helm lint success | NON VÉRIFIÉ |
| #3138 reference rename | 3 | comments and placeholders | à attribuer | Body: no runtime behaviour change. Deploy and smoke-test on that PR were SKIPPED | merged 2026-11-09T09:12:20Z, merge `8b7cc89f91797a648071654b0d098d62e6d4401c` | none runtime | PR 3138 checks | NON VÉRIFIÉ |
| HEGEMON restart on merge of #3140 | 3 | `hegemon/daemon/**` | Christophe | PR warning: merge runs `hegemon-deploy.yml` and restarts the VPS service. Keep draft until an explicit GO. No restart was performed for this matrix | #3140 draft, head `6fb12630b0f4a4fc772300508c65259220390ab9`. `hegemon/daemon/infisical-loader.sh` still on `main` | HEGEMON VPS | not run | à décider par Christophe |
| Secrets backend target for HEGEMON | 3 | `vault-loader.sh` | Christophe | On `main`, `VAULT_ADDR` defaults to `https://hcvault.gostoa.dev` (line 17). This pass did not resolve that name. OpenBao address in the helper is the SSH-tunnel default | `main` `9199b344` | not probed | source only | à décider par Christophe |
| MCP permission rollout after #3125 | 4 | control plane and gateway | à attribuer | PR body: inventory must be approved, seed rehearsed, caches expired, signed policy refreshed, allow and deny shown on CP and gateway. No DB or infra change was applied by the PR. SQL not executed. A new commit needs a new security review | merged 2026-11-06T12:54:20Z, merge `a912eea1e979d46257834579d807752a3d0d9b52`, head `a29c6aee26cf9b17fae25809cb1ee290496e0b93`. PR jobs `deploy` and `smoke-test` SKIPPED. Lint and test jobs SUCCESS | CI tests only | PR 3125 checks. No authorized-env run | NON VÉRIFIÉ |
| Combined Helm render of #3130 and #3131 | 5 | `charts/stoa-platform`, `charts/stoa-stack` | à attribuer | Render proof only | #3151 head `ae1d957ddda9db7b31894212733481ba01ba3ca2` (open). Includes `ee87112e` and `1b41cee8` | CI helm | [42693108286](https://github.com/stoa-platform/stoa/actions/runs/42693108286) job `helm / Lint Helm Charts` success, 2026-11-09T20:27:19Z. `helm / Notify stoa-infra` skipped | PASS réel |
| Helm install, upgrade, rollback | 5 | authorized test cluster | à attribuer | Not claimed by #3130, #3131, or #3151 | #3130 open, not draft, head `ee87112e3540bb2cf0a27ad27f6a5ffe6d53226d`. #3131 open draft, head `1b41cee872fca491fa5b3420255af9878d9d966c` | no cluster | PR bodies: cluster install skipped | NON VÉRIFIÉ |
| Landing order #3130 / #3131 / #3151 | 5 | chart PRs | Christophe | #3151 says: replace (merge #3151, close the other two) or follow (#3130 then updated #3131). Do not merge all three. One content conflict in `_helpers.tpl` | #3151 | n/a | PR body | à décider par Christophe |
| PostgreSQL backup/restore on a disposable database | 5 | CI Postgres 16 | à attribuer | Not a production restore. Earlier runs on the same branch failed (`42304061113`, `42403909488`) before this head passed | #3128 open, head `137ed6eda7ba56d93229f6de2902320c0088e4b7` | GHA disposable DB | [42404121499](https://github.com/stoa-platform/stoa/actions/runs/42404121499) job success, step `Run backup/restore cycle on disposable database`, 2026-11-07T19:01:03Z | PASS réel |
| Representative restore and integrity check on an authorized environment | 5 | PostgreSQL | à attribuer | Required before claiming recovery objectives | none merged | authorized env | none | NON VÉRIFIÉ |
| Recovery objectives (RPO/RTO) | 5 | PostgreSQL | Christophe | Fix the objectives before announcing they are met | none | n/a | none | à décider par Christophe |
| Redpanda loss of one broker out of three | 5 | local Compose RF3 | à attribuer | CI proof of the in-repo sizing. Not a cluster proof. Public `docs/roadmap.md` has no Redpanda or Kafka row | #3129 open, head `0519deb92758953f93e4a80329f90f231adc212d` | GHA Docker | [42304135706](https://github.com/stoa-platform/stoa/actions/runs/42304135706) job `Broker loss failover` success, 2026-11-06T22:21:52Z | PASS réel |
| Whether Redpanda belongs to the accepted milestone | 5 | M2 / M4 | Christophe | Representative proof if in scope, otherwise a motivated exclusion. Do not add it back against the accepted roadmap | #3129 | n/a | roadmap file below | à décider par Christophe |
| Keycloak HA proven | 5 | identity | à attribuer | Static checker prints `HA_STATIC=fail` while the job is green. `values-prod.yaml` `keycloak.replicas: 3` is marked REFERENCE ONLY. In-repo Compose is one replica. `--execute` is not a cluster action | #3149 open, head `60a7255ae8fddf589c3f1578682574ef64cc042c` | GHA static | [42686459119](https://github.com/stoa-platform/stoa/actions/runs/42686459119) log line 240 `HA_STATIC=fail`, 2026-11-09T19:45:53Z, job success | FAIL |
| Keycloak live failover | 5 | authorized cluster | à attribuer | Not run | #3149 | not used | script not executed against a cluster | NON VÉRIFIÉ |
| stoa-infra Keycloak HA and PostgreSQL backup shape | 5 | prod cluster | à attribuer | PRs were not readable. No replica count and no CronJob presence is asserted | https://github.com/PotoMitan/stoa-infra/pull/132 and /pull/133 | unknown | `gh api repos/PotoMitan/stoa-infra` returned HTTP 404 on this token | NON VÉRIFIÉ |
| Public roadmap vs the validated M2 milestone | 6 | stoa-docs `docs/roadmap.md` | Christophe | File at `main` `ee458a9` (blob `f552693233d59065c593aeb376044c032fe38c86`) has no M2 date and no Redpanda/Kafka line. Linear M2 date is not copied here as a docs fact. Submit doc edits for acceptance; do not move dates silently | stoa-docs `ee458a9dd7c06a4e066963bdfc413d1ab5d0f164` | public docs | `docs/roadmap.md` | à décider par Christophe |
| Explicit GO to resume feature work | 6 | recovery lock | Christophe | A merged docs PR does not close CAB-2612 | this file | n/a | none | à décider par Christophe |

### Count by status

| Statut | Rows |
|---|---|
| PASS réel | 9 — AT-0, AT-1, AT-2, AT-3, AT-4, AT-5 counter, Helm render #3151, disposable Postgres cycle, local Redpanda broker-loss |
| FAIL | 3 — dev HTTP 000 still green, Infisical init docs ahead of `main`, Keycloak `HA_STATIC=fail` |
| SKIP | 7 — prod MCP smoke, dev health smoke, CP API smoke-test, AT-5b, AT-LLM, demo authentication, live OpenBao client tests |
| NON VÉRIFIÉ | 13 |
| à décider par Christophe | 8 |

## OpenBao — only what these repositories show

Verifiable in `stoa` at `9199b344`:

- `scripts/lib/stoa-secret.sh` reads KV v2 `secret/stoa/tooling/<path>` via an SSH-tunnel default address. It does not prove the tunnel, TLS, audit, unseal, or a restore.
- `.claude/docs/secrets-management.md` still names HashiCorp Vault at `hcvault.gostoa.dev` as source of truth and OpenBao as the tooling path. Infisical is described as retired by ADR-075 (2026-11-07). ADR text itself lives in stoa-docs and was not re-certified here.
- #3134 is merged (tooling reader). #3138 is merged (wording only, per its body). #3139 is open. #3140 is an open draft. stoa-docs#236 is merged while the chart file it describes is still on `main`.
- On run 42591592425 the live OpenBao/Vault client tests were skipped because `VAULT_IT_ADDR` was not set.

Not verifiable from these reads: import of secrets, a tested backup, network path from the cluster and from CI, consumer rights, unseal procedure, or shutdown of the dev Vault. `stoa-infra` was not readable.

## Décisions Christophe en attente

1. Public MCP: real tested service, or explicit withdrawal. Do not republish it for a green check.
2. Target milestone journey, and whether legacy / UAC / LLM stays out of scope.
3. OpenBao network path and consumer cut-over. No secret change and no vault shutdown without the existing approvals.
4. GO before merging #3140. That merge restarts HEGEMON. No resume of paused runs without a GO.
5. Helm landing: #3151 replaces #3130 and #3131, or #3130 then #3131. Not all three.
6. PostgreSQL RPO/RTO before any claim they are met. Redpanda in or out of the milestone.
7. Roadmap text versus the validated milestones.
8. `MCP_PROD_SMOKE_REQUIRED` / `DEV_POST_DEPLOY_REQUIRED` defaults once #3150 and #3154 are reviewed.
9. Final GO on CAB-2612. Until that GO, the lock stays. This PR does not close the ticket.

## Reste à prouver sur environnement autorisé

- Authenticated journey with an allow and a deny, a request id, and the required observability.
- Prod MCP smoke actually executed, or a recorded non-applicability after decision 1.
- Dev post-deploy on `main` after the truthfulness fix, including a negative case that cannot stay green.
- OpenBao path, TLS, audit, unseal/restart, and a checked backup/restore.
- Approved MCP allow inventory, seed assertions, and live allow/deny on the control plane and the gateway.
- Helm install, upgrade, and rollback of the combined chart.
- PostgreSQL restore with an integrity check against the agreed objectives.
- Keycloak failover against the real topology. stoa-infra#132 and #133 still unread.
- Redpanda on that environment only if decision 6 keeps it in scope.
- A closure review separate from the implementing agent, then Christophe's GO.
