# CI controls truth inventory (CAB-2612)

Evidence collected on 2026-11-09 from `main` at `9199b3442fb8ffdb387c5cfc0934e88e867afe0f`.
Run conclusions and step conclusions come from `gh run list` / `gh run view` (read-only).
Repository variable values were not readable (Actions variables API returned 403); a
kill-switch is cited only when the step that runs solely under that `if` actually ran.

This is the historical inventory, not a fresh service-health claim. See
[CAB-2618 required checks](cab-2618-required-checks.md) for the subsequent
enforcement of MCP, health-smoke and GitOps endpoint checks. The original
MCP classification is corrected below: missing DNS does not establish an
approved retirement or non-applicability decision.

Status values:

| Status | Meaning |
| --- | --- |
| PASS réel | The check command ran and its own step succeeded. |
| FAIL | The probe failed. The job can still be green when the failure is swallowed. |
| SKIP | The check did not run. A skipped job is honest; a success wrapping a skipped probe is not. |
| NON PUBLIÉ / NA | The target is not published, or the control does not apply to that environment. |
| NON VÉRIFIÉ | No current run shows the check executing. |

Counts in the historical table below: **PASS réel 14**, **FAIL 1**, **SKIP 7**, **NON PUBLIÉ / NA 0**, **NON VÉRIFIÉ 10**.

`scripts/ci/audit_masked_controls.py` finds the same motifs statically. It always
exits 0 and is not called from any workflow.

## Inventory

| Control | Workflow | Target | Critical | Status | Proof | Proposed fix |
| --- | --- | --- | --- | --- | --- | --- |
| MCP SDK prod probe | `mcp-sdk-smoke.yml` `post-deploy` | prod `mcp.gostoa.dev` | yes | SKIP | [42583971143](https://github.com/stoa-platform/stoa/actions/runs/42583971143) success, schedule, 2026-11-09, `c4b1ea7bc801`. Smoke step skipped; availability NON VÉRIFIÉ. Pre-merge job not applicable to the cron event. | Fail closed in CAB-2618. Public-service scope remains a human decision. |
| MCP SDK pre-merge | `mcp-sdk-smoke.yml` `pre-merge` | local gateway from HEAD | yes | PASS réel | [42173378226](https://github.com/stoa-platform/stoa/actions/runs/42173378226) push, 2026-11-06, `1a327342c188`. Step `Run authenticated MCP SDK smoke` success. | None. Prod probe stays on the schedule job. |
| Dev health smoke | `reusable-health-smoke.yml` via gateway, portal, console CI | dev | yes | SKIP | Gateway [42173378271](https://github.com/stoa-platform/stoa/actions/runs/42173378271) 2026-11-06 `1a327342c188`; portal [42591211264](https://github.com/stoa-platform/stoa/actions/runs/42591211264) 2026-11-09 `303010db9877`; console [42067952395](https://github.com/stoa-platform/stoa/actions/runs/42067952395) 2026-11-05 `b3b26485db7f`. Job success. `Health checks` skipped. Warning: `SKIPPED, no dev target`. | Keep CAB-2362 (do not probe prod for a dev deploy). A `skip=true` result must not be a successful smoke job. |
| Dev GitOps endpoint verify | `reusable-gitops-deploy.yml` | dev gateway, portal, console | yes | FAIL | Same three runs. `Wait for ArgoCD sync` success after `Endpoint not healthy after 300s/180s (last: HTTP 000)`. The step has no `exit 1`. | `exit 1` when the deadline passes without HTTP 200. |
| CP API post-deploy smoke | `control-plane-api-ci.yml` `smoke-test` | prod only, by `if` | yes | SKIP | [42591592425](https://github.com/stoa-platform/stoa/actions/runs/42591592425) push success, 2026-11-09, `8b7cc89f9179`. Job `smoke-test` skipped. Main pushes deploy `dev`, and the `if` also requires `environment == prod`. | Do not treat a main push as smoked. Run the prod probe on a schedule that fails closed, or surface the skipped job. |
| CP API dev verify | `reusable-gitops-deploy.yml` from CP API CI | dev | yes | SKIP | Same run. `Wait for ArgoCD sync` skipped because `verify-endpoint` is empty for dev. | Same as the health-smoke skip: empty verify is not a pass. |
| Scheduled security backstop | `security-scheduled.yml` | repo (weekly) | yes | SKIP | [42572628376](https://github.com/stoa-platform/stoa/actions/runs/42572628376) success, 2026-11-09, `c4b1ea7bc801`. `Record disabled watcher` ran (`if: vars.DISABLE_L2_SCHEDULED == 'true'`). Trivy, dependency audit, and gitleaks jobs skipped. | A kill-switch should end the workflow as skipped, not success. |
| Weekly dependency audits | `weekly-audit.yml` | repo | yes | PASS réel | [42584930299](https://github.com/stoa-platform/stoa/actions/runs/42584930299) 2026-11-09 `c4b1ea7bc801`. pip-audit: `No known vulnerabilities found`. npm (ui, portal, e2e): `found 0 vulnerabilities`. cargo-audit: 3 allowed unmaintained warnings (`bincode`, `derivative`, `unsafe-libyaml`). | Remove job `continue-on-error` and the `\|\| true` on the audit commands so a future finding fails the run. |
| Push security scan | `security-scan.yml` | repo / images | yes | PASS réel | [42622365956](https://github.com/stoa-platform/stoa/actions/runs/42622365956) push, 2026-11-09, `9199b3442fb8`. Blocking Trivy, ESLint gate, pip/npm/cargo audits, gitleaks succeeded. SARIF upload stays `continue-on-error` and is not the gate. | None for the blocking steps. |
| Verify signed commits | `required-checks.yml` | PR and push | yes | PASS réel | [42622365904](https://github.com/stoa-platform/stoa/actions/runs/42622365904) 2026-11-09 `9199b3442fb8`. Verify step success. Job still has `continue-on-error: true` (Gate 6A). | Gate 6B, in its own change: a future unsigned commit must fail the required check. |
| License compliance | `required-checks.yml` | repo | yes | PASS réel | Same run. Self-test and offline check succeeded. Steps are `continue-on-error` unless `LICENSES_MODE` is `deny` or `enforce`. Mode was not readable. | Keep warn mode explicit. Promotion to deny/enforce is an admin change, not a silent default. |
| Image pinning guard | `required-checks.yml` | changed files | yes | PASS réel | Same run. Job success, no swallow. | None. |
| Dependency review | `dependency-review.yml` | pull requests | yes | PASS réel | [42693107838](https://github.com/stoa-platform/stoa/actions/runs/42693107838) 2026-11-09 `ae1d957ddda9` (PR, not a main push). Review step success, under `continue-on-error: true`. | Remove `continue-on-error` once GitHub Advanced Security is enabled, as the workflow comment already says. |
| Live E2E | `e2e-tests.yml` | deployed env, schedule and main push | yes | NON VÉRIFIÉ | Workflow `disabled_manually`. Last run [40827004593](https://github.com/stoa-platform/stoa/actions/runs/40827004593) schedule success, 2026-10-29, `f50c9d21dbc8`; `Run E2E tests` succeeded on all 3 shards. No run since. Schedule also sets `continue-on-error`. | Re-enable is an operator action. On the schedule, drop `continue-on-error` so a failure stays red. Push is already blocking when the workflow is enabled. |
| E2E nightly | `e2e-nightly.yml` | prod personas | yes | NON VÉRIFIÉ | Workflow `disabled_manually`. Last run [23973668589](https://github.com/stoa-platform/stoa/actions/runs/23973668589) cancelled, schedule, 2026-04-04, `96850772a6a0`. | Re-enable only with a fail-closed reusable smoke. Do not treat the file as live coverage. |
| Demo smoke | `demo-smoke.yml` | local Compose | yes | PASS réel | [42622365951](https://github.com/stoa-platform/stoa/actions/runs/42622365951) push, 2026-11-09, `9199b3442fb8`. No `::notice` and no readiness `::warning`, which the script emits only on failure. Default `DEMO_SMOKE_BLOCKING` is `false`, and a not-ready stack only warns. | Default the job to fail on a non-zero smoke exit. Keep observation as an explicit input. |
| Guardrails phase 6 | `guardrails-smoke.yml` | dispatch `dev-k3d` or prod | yes | NON VÉRIFIÉ | Workflow active. `gh run list` returned no runs. | Dispatch a dev-k3d run out of band. This PR does not dispatch it. |
| Prod promote health | `reusable-promote.yml` via `promote-to-prod.yml` | prod | yes | NON VÉRIFIÉ | Last dispatch [25423611157](https://github.com/stoa-platform/stoa/actions/runs/25423611157) success, 2026-05-06, `81e1ba891abb`, console only. Logs are outside retention. The wait loop warns and does not `exit 1`. | `exit 1` when any prod check is still failing at the deadline. |
| Rust scheduled audit | `rust-scheduled-checks.yml` | `stoa-gateway` | yes | PASS réel | [42572021662](https://github.com/stoa-platform/stoa/actions/runs/42572021662) 2026-11-09 `c4b1ea7bc801`. `cargo audit` and bench compile steps succeeded, both `continue-on-error: true`. | Drop `continue-on-error` on `cargo audit`. Leave sccache `continue-on-error` (cache only). |
| OpenSSF Scorecard | `scorecard.yml` | repo | no | PASS réel | [42622366072](https://github.com/stoa-platform/stoa/actions/runs/42622366072) 2026-11-09 `9199b3442fb8`. `Run Scorecard` succeeded. Job is `continue-on-error`. | Drop `continue-on-error` on the public repo, or accept it as advisory in the branch rules. |
| Council S3 | `council-gate.yml` | pull requests | no | SKIP | [42693107841](https://github.com/stoa-platform/stoa/actions/runs/42693107841) conclusion skipped, 2026-11-09, `ae1d957ddda9`. The review job did not start. Honest skip, not a green pass. Shadow mode would also `exit 0` when `ANTHROPIC_API_KEY` is missing. | Keep it non-blocking until the shadow window ends. A missing key should be a skipped conclusion, not exit 0 inside a green job. |
| PR Guardian | `pr-guardian.yml` | pull requests | no | SKIP | [42693571883](https://github.com/stoa-platform/stoa/actions/runs/42693571883) job success, 2026-11-09, `ae1d957ddda9`. `Post oversize notice and exit` ran; `Run STOA PR Guardian` skipped (diff cap). | Advisory by design. The oversize path is an explicit notice. Do not make it a required check. |
| SBOM generation | `required-checks.yml` | repo filesystem | no | PASS réel | [42622365904](https://github.com/stoa-platform/stoa/actions/runs/42622365904) 2026-11-09 `9199b3442fb8`. CycloneDX and SPDX steps succeeded. | None. |
| Gateway perf gate | `gateway-perf-gate.yml` | local gateway | no | PASS réel | Push baseline [42173378269](https://github.com/stoa-platform/stoa/actions/runs/42173378269) 2026-11-06 `1a327342c188`. PR benchmark [42508342359](https://github.com/stoa-platform/stoa/actions/runs/42508342359) 2026-11-08 `17e43310e5b0`, benchmark step success under `continue-on-error`. | Documented advisory. Remove `continue-on-error` only if the gate becomes required. |
| Portal and console i18n | `reusable-node-ci.yml` | PR / push build | no | PASS réel | Portal [42591211264](https://github.com/stoa-platform/stoa/actions/runs/42591211264), console [42067952395](https://github.com/stoa-platform/stoa/actions/runs/42067952395). `Check i18n keys` succeeded, step is `continue-on-error`. | Remove `continue-on-error` if i18n is part of the build contract. |
| Landing API lint | `landing-api-ci.yml` | landing-api | no | PASS réel | [42004699747](https://github.com/stoa-platform/stoa/actions/runs/42004699747) 2026-11-05 `70f39ae04229`. ruff and mypy succeeded under `continue-on-error`. pytest is not swallowed. | Drop `continue-on-error` on ruff and mypy. |
| Catalog drift | `catalog-drift.yml` | cluster and catalog | no | NON VÉRIFIÉ | Workflow `disabled_manually`. Last success [23939045910](https://github.com/stoa-platform/stoa/actions/runs/23939045910) 2026-04-03 is not evidence: every check step is `continue-on-error`. | Leave disabled until the steps fail the job. Re-enable is an operator action. |
| Arena L0 | `arena-l0.yml` | prod `mcp.gostoa.dev` | no | NON VÉRIFIÉ | Workflow `disabled_manually`. Last run [23976226352](https://github.com/stoa-platform/stoa/actions/runs/23976226352) failure, 2026-04-04. k6 is invoked with `\|\| true`. | Do not re-enable while a missed gateway still falls through to a green score. |
| E2E cross-validation | `e2e-cross-validation.yml` | live services, self-hosted | no | NON VÉRIFIÉ | Active, `workflow_dispatch` only, job `continue-on-error`. Last run [40286317344](https://github.com/stoa-platform/stoa/actions/runs/40286317344) cancelled, 2026-10-26. | No self-hosted runner is registered. A dispatch would queue, not prove the UI. |
| E2E audit report | `e2e-audit.yml` | deployed env | no | NON VÉRIFIÉ | Workflow `disabled_manually`. Last run [23732836941](https://github.com/stoa-platform/stoa/actions/runs/23732836941) cancelled, 2026-03-30. The suite step is `continue-on-error`. | Leave disabled. The report must not be a green audit. |
| O1 real-Envoy proof | `o1-envoy-real-proof.yml` | manual, local Envoy | no | NON VÉRIFIÉ | Active. No runs. | Manual acceptance. Absence of a run is not a pass. |
| STOA bench | `stoa-bench.yml` | local API, dispatch | no | NON VÉRIFIÉ | Active. No runs. Locust is invoked with `\|\| true`. | Remove `\|\| true` before anyone reads a green bench as a result. |

## Fixes by priority

No workflow file is edited in this pull request.

**P0. A green job is standing in for a probe that failed or did not run.**

1. `reusable-gitops-deploy.yml`: exit 1 when `verify-endpoint` never returns HTTP 200. Observed HTTP 000 on gateway (300s), portal (180s), and console (180s), with the step still successful.
2. `reusable-health-smoke.yml`: `skip=true` (no `SMOKE_BASE_DOMAIN_DEV`) must not complete the health job as success. Do not point a dev deploy at prod.
3. Prod MCP smoke: [PR 3150](https://github.com/stoa-platform/stoa/pull/3150). Not repeated here.
4. `security-scheduled.yml`: `DISABLE_L2_SCHEDULED` currently leaves a successful workflow whose scan jobs are skipped.
5. `control-plane-api-ci.yml`: main pushes skip `smoke-test` and skip dev verify. The workflow success is not a prod or dev smoke.

**P1. The check ran this week, but a later failure cannot turn the job red.**

1. `Verify Signed Commits` (`continue-on-error` on the required job). Latest step passed. Flipping it is Gate 6B and can turn `main` red; do it alone.
2. License steps, while `LICENSES_MODE` is not `deny` or `enforce`. Latest steps passed.
3. `weekly-audit.yml`: job `continue-on-error` and `|| true` around pip-audit, npm audit, and cargo audit.
4. `rust-scheduled-checks.yml`: `continue-on-error` on `cargo audit`.
5. `dependency-review.yml`: `continue-on-error` until GHAS is enabled.
6. `demo-smoke.yml`: non-blocking by default, and the Compose readiness probe only warns.
7. `reusable-promote.yml`: prod health timeout warns and does not fail. No promote has run since 2026-05-06.
8. `e2e-tests.yml` and `e2e-nightly.yml` are `disabled_manually`. Re-enabling them is an operator action. The schedule path of `e2e-tests.yml` is also `continue-on-error`.

**P2. Advisory or unused. Do not promote them to required checks in their current shape.**

Scorecard job `continue-on-error`. Council shadow mode and missing-key `exit 0`. PR Guardian diff cap (the job posts a notice, then skips the review). Perf PR benchmark `continue-on-error`. i18n and landing-api ruff/mypy `continue-on-error`. Catalog drift, Arena L0, and the E2E audit are disabled and their historical green or red runs are not current evidence. Guardrails phase 6, O1, and STOA bench have never run. Cross-validation is dispatch-only on a self-hosted runner that is not registered.

## Scanner

```bash
python3 scripts/ci/audit_masked_controls.py
pytest scripts/ci/tests/test_audit_masked_controls.py -q
```

The scanner reports `continue-on-error` (literal `true` or an expression), a `|| true` that is not a grep/cleanup/install fallback, a `::warning::` block with no `exit 1`, and a step `if` that depends on DNS `resolves`, `resolve.outputs.skip`, `GITOPS_DEPLOY_ENABLED`, or `DISABLE_`. It does not fail the process.
