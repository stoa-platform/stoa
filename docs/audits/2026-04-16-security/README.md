# Auth/RBAC review — evidence index

Snapshot: `main` at `b37518624f37cc00cf08582cf9865f191ffff1d5` (2026-10-27).
This index records source files, regression tests and merged changes associated
with the 2026-04-16 review. Source inspection establishes their presence; it
does not establish that tests passed or that a particular deployment runs them.

## Source and merge references

| Area | Source and regression references at this snapshot | Merged changes |
| --- | --- | --- |
| JWT issuer validation and realm key cache | `control-plane-api/src/auth/dependencies.py`; `control-plane-api/tests/test_regression_cab_2082_jwt_issuer.py`; `control-plane-api/tests/test_regression_cab_2094_issuer_internal_url.py` | [#2393](https://github.com/stoa-platform/stoa/pull/2393), [#2399](https://github.com/stoa-platform/stoa/pull/2399) |
| Environment-provided E2E credentials | `e2e/fixtures/audit-auth.ts`; `control-plane-api/tests/test_regression_cab_2083_no_hardcoded_parzival.py` | [#2394](https://github.com/stoa-platform/stoa/pull/2394), [#2396](https://github.com/stoa-platform/stoa/pull/2396) |
| CORS policy | `control-plane-api/src/main.py`; `control-plane-api/tests/test_regression_cab_2142_cors.py` | [#2450](https://github.com/stoa-platform/stoa/pull/2450) |
| Environment checks for debug configuration | `control-plane-api/src/config.py`; `control-plane-api/tests/test_regression_cab_2145_debug_flag_env_gating.py` | [#2452](https://github.com/stoa-platform/stoa/pull/2452) |
| Operator rate-limit keying | `control-plane-api/src/auth/dependencies.py`; `control-plane-api/src/middleware/rate_limit.py`; `control-plane-api/tests/test_regression_cab_2146_rate_limit_keying.py` | [#2449](https://github.com/stoa-platform/stoa/pull/2449) |

## Historical rollout evidence

[P0-01 rollout verification](P0-01-rollout-verification.md), dated 2026-04-20,
records an earlier rollout. It does not establish the version or configuration
of a deployment on 2026-10-28.

## Acceptance limits

- No platform, deployment, credential or cluster was accessed to prepare this index.
- Regression files are references, not test results. Fresh execution evidence
  must identify its source revision, environment and outcome separately.
- Current deployment provenance, effective runtime configuration, tenant
  isolation acceptance and operator rate-limit behaviour require separate evidence.
- The limiter implementation uses process-local storage; this index does not
  establish a deployment-wide rate limit or its sizing.
- Auth-flow E2E acceptance is **unverified** here. A workflow summary alone
  is insufficient: the actual test outcomes must be checked, including skipped
  tests and steps whose failures are allowed.
- This index does not declare the security review complete, certify the
  platform, or attest gateway-side authorisation.

Only references already present in public merged changes are included.
Internal acceptance records retain work in progress and environment-specific evidence.
