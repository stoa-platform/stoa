# Demo Readiness Report — 2026-04-19

UTC timestamp: `2026-04-19T12:40:54Z`

Local HEAD at run time: `ce11d0ac8018d1312da9eb3fa06cc29a7697d949`

`main` HEAD at run time: `3e57435dff98c6d75f0c3789a54c8242c90f2ac4`

Observed production gateway artifact:
- Deployed image: `ghcr.io/stoa-platform/stoa-gateway:dev-cd9941741c234f3b6fd0b6bde4afad480615aa27`
- Namespace: `stoa-system`
- Pods observed: `stoa-gateway-fcdd94774-mqllz`, `stoa-gateway-fcdd94774-rf246`

## Scope

This report covers read-only production checks run from the local repo against `*.gostoa.dev` and the OVH kubeconfig. It is intentionally split between:
- observed production state
- verification script regressions
- items requiring Claude Code confirmation or follow-up

## Executive Summary

The `edge-mcp` production path is live enough for demo preparation: Console, Portal, CP API, Gateway health, Gateway OIDC discovery, and Grafana behind `console.gostoa.dev` all responded successfully during the run.

The main confirmed red on the current demo path is OpenSearch Dashboards, which returned `HTTP 503` with body `OpenSearch Dashboards server is not ready yet`. Two security/observability gaps also remain confirmed in prod: anonymous `GET /mcp/v1/tools` returns a full tool list, and public `GET /metrics` returns `200` with `gateway_otel_spans_exported_total 0`.

Three verification scripts are currently unreliable as audit artifacts because they stop too early or have config drift. They still provide signal, but not a complete matrix.

## Commands Run

### Scripted checks

1. `bash scripts/demo/smoke-test-production.sh`
2. `bash scripts/demo/demo-dry-run.sh`
3. `bash scripts/demo/pre-demo-check.sh`

### Manual follow-up checks

1. `curl https://console.gostoa.dev/`
2. `curl https://portal.gostoa.dev/`
3. `curl https://api.gostoa.dev/health`
4. `curl https://mcp.gostoa.dev/health`
5. `curl https://mcp.gostoa.dev/mcp/v1/tools`
6. `curl -X POST https://mcp.gostoa.dev/mcp/tools/call`
7. `curl https://mcp.gostoa.dev/metrics`
8. `curl https://opensearch.gostoa.dev/`
9. `curl https://console.gostoa.dev/grafana/api/health`
10. `KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl cluster-info`
11. `KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl get ns`
12. `KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl get pods -A | rg 'gateway|mcp|stoa-gateway'`

## Results

### 1. Gaps confirmed vs supposed

#### Confirmed

- `mcp.gostoa.dev/health` returned healthy.
- `GET /mcp/v1/tools` is anonymously accessible in prod and returned a list of `41` tools.
- `POST /mcp/tools/call` without auth reached execution and returned:

```text
HTTP 500
{"content":[{"type":"text","text":"Execution failed: HTTP request failed: error sending request for url (http://fapi-echo:8889/)"}],"isError":true}
```

- `GET /admin/health` returned `401`.
- `GET /metrics` is publicly accessible and returned `200`.
- `gateway_otel_spans_exported_total` is still `0` in the public metrics output.
- `console.gostoa.dev/grafana/api/health` returned `200`.
- `opensearch.gostoa.dev/` returned:

```text
HTTP/2 503
OpenSearch Dashboards server is not ready yet
```

- OVH kube access works with explicit kubeconfig.
- Production gateway pods are running in `stoa-system`.

#### Not confirmed in this run

- Authenticated MCP invoke with tenant/demo JWTs.
- Federation flows requiring `FEDERATION_SECRET_*` and `DEMO_PASSWORD`.
- Whether the exact webMethods/Axway demo tools are visible to the authenticated `stoa-demo` audience.
- Whether CP-API writes are immediately reflected in the gateway catalog for the demo tenant.

#### Nuance

- The anonymous tool list did contain banking-related names:
  - `account-management-api`
  - `banking-services-v1-2`
  - `fapi-accounts`
  - `customer-360-api`
  - `fapi-transfers`
- The specific local CRD tool names from `tools/` such as `get-customer-by-number` were not found in the anonymous list during this run.

### 2. Regressions recent or newly surfaced by this run

#### Confirmed production regression

- OpenSearch Dashboards is currently not ready in prod. This is not a script artifact; it was reproduced directly with `curl`.

#### Script regressions or config drift

- `scripts/demo/smoke-test-production.sh` exits on the first failure because `set -e` combines badly with `check()` returning non-zero. It did not complete the full matrix after the OpenSearch `503`.
- `scripts/demo/demo-dry-run.sh` is operational enough to produce signal, but it hard-stops in Act 6 when `FEDERATION_SECRET_ALPHA` is unset.
- `scripts/demo/pre-demo-check.sh` is not currently reliable as a prod readiness artifact:
  - it uses the default kube context, which failed, while the explicit OVH kubeconfig worked
  - it defaults `GRAFANA_URL` to `https://grafana.gostoa.dev`, which did not resolve in this run
  - it exits on first `FAIL`, so it does not yield a complete GO/NO-GO matrix

### 3. Demo blockers for 2026-04-28

#### Red blockers on the critical path

- OpenSearch Dashboards `503`.
  - If the demo uses OpenSearch directly or relies on Dashboards for the investigation act, this is a real blocker.
  - If the demo can stay on Grafana-only observability, this is downgradable to yellow.

#### Yellow blockers or high-risk prerequisites

- Anonymous MCP discovery is still open.
  - This is not necessarily a blocker for the demo narrative, but it is a real audit exposure if someone explores live.

- Anonymous `tools/call` reaches execution and fails inside a backend call.
  - This confirms the defense-in-depth story only partially.
  - It also confirms an auth gap: the gateway is not hard-denying the request early.

- `gateway_otel_spans_exported_total 0`.
  - Not a functional gateway blocker.
  - A blocker if the demo depends on this exact metric in dashboards or narration.

- Demo/federation scripts cannot complete from this machine because required env vars are unset:
  - `ART3MIS_PASSWORD`
  - `PARZIVAL_PASSWORD`
  - `FEDERATION_SECRET_ALPHA`
  - `FEDERATION_SECRET_BETA`
  - `FEDERATION_SECRET_GAMMA`
  - `DEMO_PASSWORD`
  - `INFISICAL_TOKEN`

- mTLS section in `demo-dry-run.sh` failed with `invalid_client` even though `credentials.json` and `fingerprints.csv` existed.
  - This is a real finding until disproved.
  - It may be a drift between seeded demo credentials and current Keycloak/client state.

#### Green on the current path

- Console reachable
- Portal reachable
- CP API health
- Gateway health
- Gateway OIDC discovery
- Grafana behind console
- OVH kube API reachable with explicit config
- Production gateway pods running

### 4. Tickets to create or update before the demo

#### Existing tickets already justified by this run

- `CAB-2092` — public `/metrics`
  - confirmed

- `CAB-2093` — `gateway_otel_spans_exported_total 0`
  - confirmed

#### Likely missing tickets or runbook fixes

- Fix `scripts/demo/smoke-test-production.sh` so it produces a full report even when one check fails.
- Fix `scripts/demo/pre-demo-check.sh`:
  - explicit OVH kubeconfig support
  - current Grafana URL/path
  - non-fatal aggregation instead of first-fail exit
- Fix `scripts/demo/demo-dry-run.sh` so missing secrets degrade cleanly into `SKIP` instead of aborting the whole run.
- OpenSearch Dashboards readiness incident or bug ticket if none exists yet.
- Demo readiness ticket for verifying the live visibility and invocation path of the webMethods/Axway banking tools as seen by `stoa-demo`.
- Demo readiness ticket for the mTLS `invalid_client` drift if this act is still in scope.

## Raw Script Signal

### `smoke-test-production.sh`

Observed before abort:
- PASS Console HTTPS reachable
- PASS CP API health
- PASS Portal HTTPS reachable
- PASS Gateway `/health`
- PASS Gateway OIDC discovery
- PASS Grafana reachable
- PASS Grafana login
- FAIL OpenSearch Dashboards HTTPS

Abort reason:
- script stopped on first fail

### `demo-dry-run.sh`

Observed before abort:
- PASS Console accessible
- PASS API health
- PASS Keycloak reachable
- PASS OIDC discovery
- FAIL Token issuance (`art3mis`) — no token returned
- PASS Portal accessible
- PASS Gateway health
- PASS credentials.json present
- PASS fingerprints.csv present
- FAIL mTLS token acquisition — `invalid_client`
- PASS Grafana health
- FAIL OpenSearch Dashboards — `HTTP 503`

Abort reason:
- missing `FEDERATION_SECRET_ALPHA`

### `pre-demo-check.sh`

Observed before abort:
- FAIL Kubernetes cluster unreachable

Manual follow-up disproved the service assumption:
- kube API is reachable with `KUBECONFIG=$HOME/.kube/config-stoa-ovh`

## Claude Verification Checklist

Claude Code should verify these items in priority order:

1. Confirm whether OpenSearch `503` is a current prod incident or an expected transient bootstrap state.
2. Confirm whether the demo can run Grafana-only if OpenSearch remains unavailable.
3. Re-run MCP checks with valid `stoa-demo` credentials and record:
   - authenticated tool count
   - presence of the webMethods/Axway banking tools
   - one successful end-to-end invoke on the demo tenant
4. Confirm whether the anonymous `tools/call` path should be treated as a blocker or a known gap with acceptable demo workaround.
5. Verify the mTLS `invalid_client` finding with current seeded credentials and Keycloak client state.
6. Fix the three verification scripts so the next run produces a complete artifact without manual salvage.
7. Check whether the gateway catalog source gap affects the exact demo write/read flow.

## Current Verdict

Verdict at `2026-04-19T12:40:54Z`:
- Core edge gateway path: `GREEN`
- Demo environment automation/runbooks: `YELLOW`
- Security posture on MCP discovery and metrics: `YELLOW/RED`
- OpenSearch observability path: `RED`

If the April 28 demo depends on OpenSearch Dashboards or on a live authenticated banking-tool invoke that has not yet been revalidated with real secrets, the demo is not ready to call `GO` without follow-up.

If the demo can stay on Console + Gateway + Grafana and the banking-tool invoke is revalidated quickly with proper credentials, the current state is recoverable.
