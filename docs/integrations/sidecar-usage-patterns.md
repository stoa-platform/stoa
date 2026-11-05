# Sidecar (Companion) Usage Patterns and Limits

This page describes how the STOA sidecar mode is used as a companion to an
existing runtime: next to a third-party gateway, next to an application, and in
a service mesh. For each pattern it gives the call flow, what STOA decides and
what the host keeps, and the current product limits as they exist in the code.

It does not describe how to choose between gateway modes. For the deployment
contract see [`specs/gateway-sidecar-contract.md`](../../specs/gateway-sidecar-contract.md);
for a step-by-step webMethods deployment see
[WebMethods Gateway + STOA Sidecar Integration](./webmethods-sidecar-integration.md).

## What Sidecar Mode Is in the Code

- Same `stoa-gateway` binary, started with `STOA_GATEWAY_MODE=sidecar`. It
  listens on `STOA_PORT` (default `8080` in every mode); the Helm chart sets
  `8081`.
- Routes: `POST /authz`, plus the routes common to every mode (`/health`,
  `/health/live`, `/health/ready`, `/ready`, `/metrics`, `/admin/*`). No `/mcp`
  route is mounted.
- `/authz` is a decision endpoint. STOA never sees or forwards backend traffic
  in this mode; the host does.
- The decision is computed by the shared `DecisionEngine`
  (`stoa-gateway/src/mode/decision.rs`). `SidecarService`
  (`stoa-gateway/src/mode/sidecar.rs`) only converts the request and formats
  the response.

### The `/authz` request

The host must send a `POST` with a JSON body in the `AuthzRequest` shape:

```json
{
  "method": "GET",
  "path": "/api/v1/orders",
  "headers": {"x-request-source": "edge"},
  "source_ip": "192.0.2.10",
  "tenant_id": "tenant-a",
  "user": {
    "id": "user-123",
    "roles": ["viewer"],
    "scopes": ["orders:read"]
  },
  "context": {}
}
```

Only `method` and `path` are required by the parser. Without `user` the
decision is `401`; without `tenant_id` it is `403`.

### The decision pipeline

The engine runs these stages in order and stops at the first denial:

| Stage | Runs when | Denial |
|-------|-----------|--------|
| `identity` | Always | `401` if `user` is absent |
| `tenant` | Always | `403` if `tenant_id` is absent |
| `consumer_rate_limit` | `quota_enforcement_enabled=true` | `429`, key `<tenant_id>:<user.id>` |
| `scope_enforcement` | Required scopes are configured (see limits) | `403` if the user holds none of them |

On allow, the engine computes headers for the upstream request: `X-User-ID`,
`X-Tenant-ID`, `X-Request-ID`, and `X-User-Scopes` / `X-User-Roles` when
non-empty.

## Responsibility Split

| Concern | Host (gateway or application) keeps | STOA sidecar decides |
|---------|-------------------------------------|----------------------|
| Authentication, token validation | Yes. STOA trusts `user` as pre-validated. | No token check on `/authz`. |
| Tenant resolution | Extracts the tenant and sends `tenant_id`. | Denies when it is missing. |
| Consumer rate limit | Its own limits, if any. | Per tenant and user, when quota enforcement is on. |
| Required scopes | Its own checks, if any. | Only if wired (not today, see limits). |
| Routing, TLS, upstream call, retries, transformation | Yes. | No. |
| Enforcing the verdict | Yes. Must refuse to forward on a non-2xx answer. | Returns a verdict only. |
| Behaviour when STOA is unreachable | Yes. Fail-open or fail-closed is host configuration. | Cannot influence it. |
| Header enrichment | Applies headers it receives. | Computes them (delivery limited, see limits). |

## Pattern 1: Next to a Third-Party Gateway

This is the supported pattern and the only one the sidecar contract calls a
real sidecar: the gateway container and `stoa-sidecar` run in the same
Kubernetes pod.

```text
Client ──▶ Third-party gateway ──(1) POST /authz, JSON──▶ stoa-sidecar
                  │                                       127.0.0.1:8081
                  │◀─────────────(2) allow / deny──────────────┘
                  │
                  └──(3) if allowed──▶ Backend API
```

1. The gateway authenticates the client and resolves the tenant.
2. Before forwarding, it calls `http://127.0.0.1:8081/authz` with the JSON body.
3. It forwards to the backend only on a `200`; otherwise it returns the
   denial status to the client.

What exists to support it:

- The Helm chart renders the two-container pod and refuses to render
  `stoaSidecar.enabled=true` unless `stoaSidecar.mainGateway.enabled=true`.
- The chart sets `STOA_PORT=8081` and `STOA_HOST=127.0.0.1`, but the HTTP
  listener does not use `STOA_HOST`: it always binds `0.0.0.0:<STOA_PORT>`, so
  `/authz` is reachable on the pod IP, not only from inside the pod. The
  gateway Service exposes the gateway port. When
  `stoaSidecar.serviceMonitor.enabled=true`, a separate ClusterIP Service
  (`*-stoa-sidecar`, used by the ServiceMonitor) targets port `8081`, the same
  listener that serves `/authz`.
- The gateway receives `EXT_AUTHZ_URL=http://localhost:8081/authz`.

What the host must provide: a plugin, policy callout or script that builds the
JSON body and calls `/authz`. The repository ships no host-side plugin.
Integrations that forward the original request as-is (method, path and headers,
no JSON body) do not match the `/authz` contract without that step.

A STOA process that targets a remote gateway is a standalone link, not a
sidecar (see the contract, section 2.2).

## Pattern 2: Next to an Application

An application, or a small proxy in front of it, can call `/authz` on
localhost before handling a request. The endpoint does not check who the
caller is.

```text
Client ──▶ Application (or local proxy) ──(1) POST /authz──▶ stoa (127.0.0.1)
                  │◀───────────────(2) allow / deny──────────────┘
                  └──(3) if allowed: handle the request
```

In this pattern the application takes over every host responsibility listed
above, including authentication and the fail-open/fail-closed choice.

Current status:

- Not covered by the sidecar contract, which requires a third-party gateway
  container. Do not label it `stoa.io/deployment-kind=sidecar`.
- No chart support: the chart guardrail requires `mainGateway.enabled=true`.
- No topology value fits it: the canonical values are `native-edge`,
  `remote-agent` and `same-pod` (gateway target plus sidecar).

## Pattern 3: In a Service Mesh

There is no mesh adapter. The shared engine and the contract both describe
mesh adapters as future work. Two building blocks exist today:

1. **Envoy HTTP response format** in `SidecarService`: allow is a bare `200`
   with headers prefixed `x-ext-authz-`, deny is a JSON error with the policy
   name. It cannot be selected at runtime (see limits).
2. **Envoy gRPC authorization listener**, enabled by `STOA_EXT_AUTHZ_GRPC_ADDR`
   (`stoa-gateway/src/authz/ext_authz_grpc.rs`). It is started independently
   of `STOA_GATEWAY_MODE` and implements `envoy.service.auth.v3.Authorization`.

```text
Client ──▶ Envoy proxy ──(1) gRPC Check──▶ STOA authorization listener
                │◀────────(2) OK / Denied──────────┘
                └──(3) if OK──▶ Workload
```

Unlike `/authz`, the gRPC listener validates the bearer JWT itself against
`STOA_EXT_AUTHZ_AUDIENCE`. It requires every scope in
`STOA_EXT_AUTHZ_REQUIRED_SCOPES`, and requires the token tenant to match
`tenant_id` in the route `context_extensions`. It strips client-supplied
identity headers, then calls the same `DecisionEngine`. It is fail-closed: a
missing audience, token, tenant or scope is a denial, and `/ready` reports
not ready when the audience is missing.

Current status:

- The gateway does not generate mesh or Envoy configuration. Whatever
  configures Envoy must set `tenant_id` (and optionally `api_id`) in
  `context_extensions` for each route.
- The gRPC listener has no TLS; the gateway warns when it is bound to a
  non-loopback address.
- Nothing in the code targets non-Envoy meshes.

## Current Product Limits

These are stated from the code on `main`, not from the roadmap.

1. **Response format is fixed to status code.** `SidecarSettings::from_env()`
   always selects `DecisionFormat::StatusCode`. The host receives only `200`,
   `401`, `403` or `429`, with no body. Enrichment headers, `X-RateLimit-*`
   headers and the denial reason are dropped. The JSON, Envoy and Kong
   formatters exist and are unit-tested, but no setting reaches them.
2. **Identity comes only from the JSON body.** `STOA_USER_INFO_HEADER`,
   `STOA_TENANT_ID_HEADER` and `STOA_UPSTREAM_TYPE` are read into settings but
   not used by `/authz`.
3. **No token validation on `/authz`, and no loopback-only listener.** Any
   caller that can reach the port can assert any identity. The HTTP listener
   binds `0.0.0.0:<STOA_PORT>`; `STOA_HOST` is read but not used for binding,
   so it cannot restrict `/authz` to loopback. `/metrics` and `/authz` share
   one port, so the `*-stoa-sidecar` metrics Service also exposes `/authz`
   inside the cluster. The chart ships no NetworkPolicy for the sidecar, and
   `STOA_IP_BLOCKLIST` is a blocklist, not an allowlist. Isolation must come
   from the network, for example a NetworkPolicy that admits only the metrics
   scraper on port `8081`.
4. **Scope enforcement is not wired in sidecar mode.** The router never sets
   required scopes on the sidecar engine; only the gRPC listener uses
   `STOA_EXT_AUTHZ_REQUIRED_SCOPES`. Where the engine does check scopes, one
   matching scope is enough; the gRPC listener adds its own all-scopes check.
5. **No policy-engine evaluation in the decision.** The engine stages are
   identity, tenant, rate limit and scope. Policies managed in the Control
   Plane are not evaluated by `/authz` today.
6. **Rate limits are per process.** The consumer rate limiter keeps its token
   buckets in memory, so each sidecar instance counts separately.
7. **No per-decision usage event.** The decision metadata (request ID, stages
   evaluated, evaluation time) is only returned in the response, and is
   dropped by the default format. The generic HTTP metrics (and the access log,
   when enabled) record the `/authz` call itself; there are no sidecar-specific
   decision metrics in the code.
8. **Request body and `context` are not inspected.** `AuthzRequest` carries no
   body field, and `context` is passed through without being evaluated.
9. **No application or mesh packaging.** Patterns 2 and 3 have no chart,
   label or topology value, and no mesh adapter exists.

## Related

- [Sidecar contract](../../specs/gateway-sidecar-contract.md)
- [Gateway topology normalization](../../specs/gateway-topology-normalization.md)
- [WebMethods Gateway + STOA Sidecar Integration](./webmethods-sidecar-integration.md)
- [Sidecar and stoa-connect Observability Wiring](../observability/sidecar-connect-wiring.md)
