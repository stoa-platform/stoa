# Standalone gateway

Run `stoa-gateway` without control-plane-api. Contracts come from stoactl
through `POST /admin/contracts`. This directory is the k3s example for that
mode: namespace `stoa`, ingress-nginx class `nginx`, one node.

`jwt-proof.sh` is the published-route JWT check (Keycloak plus nginx). It is
unchanged.

## Keycloak issuer

`STOA_KEYCLOAK_URL` is the **issuer base**. The validator expects

```text
iss = {STOA_KEYCLOAK_URL}/realms/{STOA_KEYCLOAK_REALM}
```

Tokens minted at `https://auth.gostoa.dev` carry
`iss=https://auth.gostoa.dev/realms/stoa`. The in-cluster address must not
be `STOA_KEYCLOAK_URL`, or those tokens fail issuer checks.

`STOA_KEYCLOAK_INTERNAL_URL` is only the fetch base. Discovery and JWKS keep
their path and swap scheme plus host, so the pod calls

```text
http://keycloak.stoa.svc:8080/realms/stoa/.well-known/openid-configuration
```

while `iss` stays `https://auth.gostoa.dev/realms/stoa`. `STOA_JWT_ISSUER` is
not read by the validator.

The example ConfigMap therefore sets:

| Variable | Value |
| --- | --- |
| `STOA_KEYCLOAK_URL` | `https://auth.gostoa.dev` |
| `STOA_KEYCLOAK_INTERNAL_URL` | `http://keycloak.stoa.svc:8080` |
| `STOA_KEYCLOAK_REALM` | `stoa` |

Change the realm if `auth.gostoa.dev` uses a different one. Readiness
(`/ready`) calls discovery on the internal URL and stays 503 until Keycloak
answers. Liveness is `/health` and does not call Keycloak or the control plane.

## Apply

Parameters live in `params.env` (node hostname, namespace, public host, image):

```bash
# defaults: hostname vmi3109795, namespace stoa, host gateway.gostoa.dev
deploy/standalone/apply.sh --print
kubectl -n stoa create secret generic stoa-gateway-admin \
  --from-literal=STOA_ADMIN_API_TOKEN="$(openssl rand -hex 32)"
deploy/standalone/apply.sh
```

`secret.yaml` is a template (`REPLACE_FROM_VAULT`). `apply.sh` does not apply
it. The Deployment reads `STOA_ADMIN_API_TOKEN` from Secret
`stoa-gateway-admin`, not from the ConfigMap.

`STOA_ENVIRONMENT` is `dev`. `prod` and `staging` refuse to boot unless
`STOA_POLICY_PATH` points at an existing Rego file (`stoa-gateway/policies/default.rego`
is not in the image).

## Admin API is not on the Ingress

The process listens on 8080 only. There is no admin port. The Ingress publishes
`/apis`, `/mcp`, `/.well-known`, `/oauth`, `/health`, and `/ready`. It has no
`/` prefix and no `/admin` rule, so the public hostname does not route the
admin API.

Inside the cluster, stoactl uses the separate Service (also not an Ingress
backend):

```text
http://stoa-gateway-admin.stoa.svc:8080/admin/contracts
```

Unset or empty `STOA_ADMIN_API_TOKEN` makes `/admin` return 503. A missing or
wrong bearer returns 401. There is no default token.

## Trusted proxies

`STOA_TRUSTED_PROXIES` (not `STOA_MTLS__TRUSTED_PROXIES`) is the allow list for
`X-Forwarded-For` and `X-Forwarded-Proto`. The TCP peer must sit in the list.
On this cluster that peer is the ingress-nginx pod, so the list includes pod
CIDR `10.42.0.0/16` plus the Cloudflare ranges fetched on 2026-10-21 from
`https://www.cloudflare.com/ips-v4` and `https://www.cloudflare.com/ips-v6`.

The client is the first address from the right that is not itself trusted, so
a spoofed leftmost hop is ignored. Scheme comes from `X-Forwarded-Proto` only
for a trusted peer. An empty list keeps the old leftmost-`X-Forwarded-For`
behaviour and does not trust the proto header.

Refresh the Cloudflare ranges before the next change; they are copied into
`configmap.yaml`.

## Image

No image of this branch is published. `ghcr.io/stoa-platform/stoa-gateway` is
not updated from this PR. Build locally and import into k3s (containerd):

```bash
docker build -t stoa-gateway:0.9.25 stoa-gateway
docker image inspect --format '{{.Id}}' stoa-gateway:0.9.25
docker save stoa-gateway:0.9.25 | sudo k3s ctr images import -
```

`params.env` pins the image built from this branch on 2026-10-21:

```text
stoa-gateway@sha256:a8257c8f10341845343c72599aefc87b23a0f52bf38e14136eea4a6641a029fb
```

That is the local image id (`docker image inspect --format '{{.Id}}'`). Nothing
was pushed, so `ghcr.io` has no manifest for it. `imagePullPolicy` is
`IfNotPresent`. After `k3s ctr images import`, check `sudo k3s ctr images ls`.
If containerd reports a different digest, put that digest in `params.env`.

The Dockerfile is the three-stage cargo-chef build in `stoa-gateway/Dockerfile`
(`rust:1.93-bookworm`, runtime `debian:bookworm-slim`, user 1000). Base image
tags are not digest-pinned. `stoa-gateway/.dockerignore` excludes `target/`
so the context is not the local debug build.

## Startup without control-plane-api

Leave `STOA_CONTROL_PLANE_URL` unset. The process then:

- skips auto-registration and heartbeats (also skipped when the API key is unset)
- does not pre-warm connections to a control plane
- does not start the 60s tool-discovery or API-catalog refresh loops
- does not start route reload (`STOA_ROUTE_RELOAD_ENABLED` defaults off; the
  example sets it false anyway)

`/health` does not call the control plane. A blank URL is treated as unset.
`AppState` still builds an internal client aimed at `http://localhost:8000`
for tools that are invoked later; nothing dials it at startup when the URL is
unset.

`prod` / `staging` without a policy file exits immediately. That is a config
panic, not a control-plane retry.

## Environment variables

Figment reads `STOA_<FIELD>` and nested fields with `__`
(`STOA_MTLS__ENABLED`). Booleans are `true` / `false`. Lists accept a CSV
string or a JSON array. Legacy names without the prefix are listed at the
end. Secrets are never given a default.

### Server and auth

| Variable | Default | Notes |
| --- | --- | --- |
| `STOA_PORT` | `8080` | Listen port. Admin is on this port. |
| `STOA_HOST` | `0.0.0.0` | Bind address. |
| `STOA_JWT_SECRET` | unset | Legacy HMAC secret. RS256 uses Keycloak. |
| `STOA_JWT_ISSUER` | unset | Stored, not used for issuer checks. |
| `STOA_KEYCLOAK_URL` | unset | Public issuer base. |
| `STOA_KEYCLOAK_REALM` | `stoa` when URL set | Appended as `/realms/{realm}`. |
| `STOA_KEYCLOAK_CLIENT_ID` | `stoa-mcp-gateway` when URL set | Audience label. Audience check is off. |
| `STOA_KEYCLOAK_CLIENT_SECRET` | unset | Gateway's own client, not the caller. |
| `STOA_KEYCLOAK_ADMIN_PASSWORD` | unset | DCR public-client patch. |
| `STOA_KEYCLOAK_INTERNAL_URL` | unset | Discovery and JWKS fetch base. |
| `STOA_GATEWAY_EXTERNAL_URL` | `http://localhost:8080` | Advertised OAuth base. |
| `STOA_ADMIN_API_TOKEN` | unset | Unset → admin 503. Wrong bearer → 401. |
| `STOA_TRUSTED_PROXIES` | empty | CSV/JSON CIDRs for client IP and scheme. |

### Control plane and audit

| Variable | Default | Notes |
| --- | --- | --- |
| `STOA_CONTROL_PLANE_URL` | unset | Unset → standalone. No refresh loops. |
| `STOA_CONTROL_PLANE_API_KEY` | unset | Required together with the URL to register. |
| `STOA_AUDIT_SPOOL_DIR` | `/var/lib/stoa-gateway/audit-spool` | Example mounts an emptyDir. |
| `STOA_AUDIT_SPOOL_CAPACITY_BYTES` | `67108864` | |
| `STOA_AUDIT_SPOOL_SEGMENT_BYTES` | `1048576` | |
| `STOA_AUDIT_SPOOL_HIGH_WATER_PCT` | `80` | |

### Git sync

| Variable | Default |
| --- | --- |
| `STOA_GITLAB_URL` | unset |
| `STOA_GITLAB_API_URL` | unset |
| `STOA_GITLAB_TOKEN` | unset |
| `STOA_GITLAB_PROJECT_ID` | unset |
| `STOA_GITHUB_TOKEN` | unset |
| `STOA_GITHUB_ORG` | unset |
| `STOA_GITHUB_CATALOG_REPO` | unset |
| `STOA_GITHUB_GITOPS_REPO` | unset |
| `STOA_GITHUB_WEBHOOK_SECRET` | unset |
| `STOA_GIT_PROVIDER` | `gitlab` (`gitlab` or `github`) |

### MCP, rate limit, policy, logs

| Variable | Default | Notes |
| --- | --- | --- |
| `STOA_RATE_LIMIT_DEFAULT` | `1000` | |
| `STOA_RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `STOA_MCP_SESSION_TTL_MINUTES` | `30` | |
| `STOA_WEBSOCKET_ENABLED` | `false` | |
| `STOA_WS_PROXY_ENABLED` | `false` | |
| `STOA_WS_PROXY_RATE_LIMIT_PER_SECOND` | `100` | |
| `STOA_WS_PROXY_RATE_LIMIT_BURST` | `50` | |
| `STOA_POLICY_PATH` | unset | Required file when environment is `prod` or `staging`. |
| `STOA_POLICY_ENABLED` | `true` | `false` panics in `prod` / `staging`. |
| `STOA_LOG_LEVEL` | `info` | Hint. The subscriber uses `RUST_LOG`. |
| `STOA_LOG_FORMAT` | `json` | `json`, `pretty`, or `compact`. |
| `STOA_OTEL_ENDPOINT` | unset | Unset → no export. |
| `STOA_OTEL_ENABLED` | `true` | |
| `STOA_OTEL_SAMPLE_RATE` | `1.0` | |
| `STOA_DETAILED_TRACING` | `false` | |
| `STOA_PROXY_METRICS_ENABLED` | `true` | |
| `STOA_PROXY_TRACING_ENABLED` | `true` | |
| `RUST_LOG` | `info,stoa_gateway=debug` if unset | Not a `STOA_` key. Example sets `info,stoa_gateway=info`. |

### Mode, governance, registration

| Variable | Default | Notes |
| --- | --- | --- |
| `STOA_GATEWAY_MODE` | `edge-mcp` | `edge-mcp`, `sidecar`, `proxy`, `shadow`. |
| `STOA_ZOMBIE_DETECTION_ENABLED` | `true` | |
| `STOA_AGENT_SESSION_TTL_SECS` | `600` | |
| `STOA_ATTESTATION_INTERVAL` | `100` | |
| `STOA_SHADOW_CAPTURE_SOURCE` | unset | `inline`, `envoy-tap`, `port-mirror`, `kafka`. |
| `STOA_SHADOW_MIN_SAMPLES` | `10` | |
| `STOA_SHADOW_GITLAB_PROJECT` | unset | |
| `STOA_ENVIRONMENT` | `dev` | `dev`, `staging`, `prod`. |
| `STOA_AUTO_REGISTER` | `true` | No-op without URL and API key. |
| `STOA_ADVERTISE_URL` | unset | |
| `STOA_HEARTBEAT_INTERVAL_SECS` | `30` | Only while registration is running. |
| `STOA_TARGET_GATEWAY_URL` | unset | |
| `STOA_GATEWAY_PUBLIC_URL` | unset | |
| `STOA_GATEWAY_UI_URL` | unset | |
| `STOA_DEPLOYMENT_MODE` | unset | `edge`, `connect`, `sidecar`. |
| `STOA_TARGET_GATEWAY_TYPE` | unset | |
| `STOA_TOPOLOGY` | unset | |
| `STOA_TOPOLOGY_PROOF` | unset | JSON string. |
| `STOA_NATIVE_TOOLS_ENABLED` | `true` | Example sets `false`. |
| `STOA_INSTANCE_NAME` | unset | Read directly. Registration hostname override. |

### Kafka, Kubernetes watcher, quota

| Variable | Default |
| --- | --- |
| `STOA_KAFKA_ENABLED` | `false` |
| `STOA_KAFKA_BROKERS` | `redpanda:9092` |
| `STOA_KAFKA_METERING_TOPIC` | `stoa.metering` |
| `STOA_KAFKA_ERRORS_TOPIC` | `stoa.errors` |
| `STOA_KAFKA_DEPLOY_PROGRESS_TOPIC` | `stoa.deployment.progress` |
| `STOA_K8S_ENABLED` | `false` |
| `STOA_KAFKA_CNS_ENABLED` | `false` |
| `STOA_KAFKA_CNS_TOPICS` | `stoa.api.lifecycle,stoa.deployment.events,stoa.security.alerts,stoa.policy.changes` |
| `STOA_KAFKA_CNS_CONSUMER_GROUP` | `stoa-gateway-cns` |
| `STOA_QUOTA_ENFORCEMENT_ENABLED` | `false` |
| `STOA_QUOTA_SYNC_INTERVAL_SECS` | `60` |
| `STOA_QUOTA_DEFAULT_RATE_PER_MINUTE` | `60` |
| `STOA_QUOTA_DEFAULT_DAILY_LIMIT` | `10000` |
| `STOA_ACCESS_LOG_ENABLED` | `true` |
| `STOA_ROUTE_RELOAD_ENABLED` | `false` |
| `STOA_ROUTE_RELOAD_INTERVAL_SECS` | `30` |

### Guardrails, RAG, budgets, tools

| Variable | Default |
| --- | --- |
| `STOA_GUARDRAILS_PII_ENABLED` | `false` |
| `STOA_GUARDRAILS_PII_REDACT` | `true` |
| `STOA_GUARDRAILS_INJECTION_ENABLED` | `false` |
| `STOA_GUARDRAILS_CONTENT_FILTER_ENABLED` | `false` |
| `STOA_PROMPT_GUARD_ENABLED` | `false` |
| `STOA_PROMPT_GUARD_ACTION` | `block` |
| `STOA_RAG_INJECTOR_ENABLED` | `false` |
| `STOA_RAG_MAX_CONTEXT_LENGTH` | `4096` |
| `STOA_RAG_SOURCE_TIMEOUT_MS` | `3000` |
| `STOA_RAG_MAX_CHUNKS` | `5` |
| `STOA_TOKEN_BUDGET_ENABLED` | `false` |
| `STOA_TOKEN_BUDGET_DEFAULT_LIMIT` | `500000` |
| `STOA_TOKEN_BUDGET_WINDOW_HOURS` | `1` |
| `STOA_FALLBACK_ENABLED` | `false` |
| `STOA_FALLBACK_CHAINS` | unset |
| `STOA_FALLBACK_TIMEOUT_MS` | `5000` |
| `STOA_CLASSIFICATION_ENFORCEMENT_ENABLED` | `false` |
| `STOA_TOOL_REFRESH_TTL_SECS` | `300` |
| `STOA_TOOL_MAX_STALENESS_SECS` | `1800` |
| `STOA_TOOL_EXPANSION_MODE` | `coarse` (`coarse` or `per-op`) |
| `STOA_CB_FAILURE_THRESHOLD` | `5` |
| `STOA_CB_RESET_TIMEOUT_SECS` | `30` |
| `STOA_CB_SUCCESS_THRESHOLD` | `2` |
| `STOA_SKILL_CONTEXT_ENABLED` | `false` |
| `STOA_SKILL_CACHE_TTL_SECS` | `300` |
| `STOA_SKILL_CONTEXT_MAX_BYTES` | `8192` |
| `STOA_SKILL_CONTEXT_HEADER` | `X-Skill-Context` |
| `STOA_FEDERATION_ENABLED` | `false` |
| `STOA_FEDERATION_CACHE_TTL_SECS` | `300` |
| `STOA_FEDERATION_CACHE_MAX_ENTRIES` | `10000` |
| `STOA_FEDERATION_UPSTREAMS` | `[]` JSON array (`url`, optional `transport`, `auth_token`, `timeout_secs`) |
| `STOA_PROMPT_CACHE_MAX_ENTRIES` | `1000` |
| `STOA_PROMPT_CACHE_TTL_SECS` | `3600` |
| `STOA_PROMPT_CACHE_WATCH_DIR` | unset |
| `STOA_BUDGET_ENFORCEMENT_ENABLED` | `false` |
| `STOA_BUDGET_CACHE_TTL_SECS` | `60` |
| `STOA_BILLING_API_URL` | unset (falls back to the control-plane URL) |
| `STOA_MCP_DISCOVERY_CACHE_TTL_SECS` | `300` |
| `STOA_MCP_DISCOVERY_CACHE_MAX_ENTRIES` | `256` |

### LLM, supervision, protocol bridges

| Variable | Default |
| --- | --- |
| `STOA_LLM_ENABLED` | `false` |
| `STOA_LLM_DEFAULT_TIMEOUT_MS` | `30000` |
| `STOA_LLM_ROUTER__ENABLED` | `false` |
| `STOA_LLM_ROUTER__DEFAULT_STRATEGY` | `round_robin` |
| `STOA_LLM_ROUTER__BUDGET_LIMIT_USD` | `0` |
| `STOA_LLM_ROUTER__PROVIDERS` | `[]` |
| `STOA_LLM_ROUTER__SUBSCRIPTION_MAPPING` | empty map |
| `STOA_SUPERVISION_ENABLED` | `false` |
| `STOA_SUPERVISION_WEBHOOK_URL` | unset |
| `STOA_SUPERVISION_DEFAULT_TIER` | `autopilot` |
| `STOA_LLM_PROXY_ENABLED` | `false` |
| `STOA_LLM_PROXY_UPSTREAM_URL` | `https://api.anthropic.com` |
| `STOA_LLM_PROXY_API_KEY` | unset |
| `STOA_LLM_PROXY_TIMEOUT_SECS` | `300` |
| `STOA_LLM_PROXY_METERING_URL` | unset |
| `STOA_LLM_PROXY_PROVIDER` | unset (`anthropic`, `mistral`, `openai`) |
| `STOA_LLM_PROXY_MISTRAL_API_KEY` | unset |
| `STOA_LLM_PROXY_MISTRAL_UPSTREAM_URL` | `https://api.mistral.ai` |
| `STOA_LLM_PROXY_SKIP_VALIDATION` | `false` |
| `STOA_API_PROXY__ENABLED` | `false` |
| `STOA_API_PROXY__REQUIRE_AUTH` | `true` |
| `STOA_API_PROXY__BACKENDS__<NAME>__ENABLED` | `false` |
| `STOA_API_PROXY__BACKENDS__<NAME>__BASE_URL` | required when that backend is set |
| `STOA_API_PROXY__BACKENDS__<NAME>__AUTH_TYPE` | `bearer` |
| `STOA_API_PROXY__BACKENDS__<NAME>__AUTH_HEADER` | `Authorization` |
| `STOA_API_PROXY__BACKENDS__<NAME>__RATE_LIMIT_RPM` | `0` |
| `STOA_API_PROXY__BACKENDS__<NAME>__TIMEOUT_SECS` | `30` |
| `STOA_API_PROXY__BACKENDS__<NAME>__CIRCUIT_BREAKER_ENABLED` | `true` |
| `STOA_API_PROXY__BACKENDS__<NAME>__FALLBACK_DIRECT` | `false` |
| `STOA_API_PROXY__BACKENDS__<NAME>__ALLOWED_PATHS` | empty |
| `STOA_HEGEMON_ENABLED` | `false` |
| `STOA_HEGEMON_BUDGET_DAILY_USD` | `50` |
| `STOA_HEGEMON_BUDGET_WARN_PCT` | `0.8` |
| `STOA_A2A_ENABLED` | `false` |
| `STOA_A2A_MAX_AGENTS` | `1000` |
| `STOA_A2A_MAX_TASKS` | `10000` |
| `STOA_SOAP_PROXY_ENABLED` | `false` |
| `STOA_SOAP_BRIDGE_ENABLED` | `false` |
| `STOA_GRPC_PROXY_ENABLED` | `false` |
| `STOA_GRPC_BRIDGE_ENABLED` | `false` |
| `STOA_GRAPHQL_PROXY_ENABLED` | `false` |
| `STOA_GRAPHQL_BRIDGE_ENABLED` | `false` |
| `STOA_KAFKA_BRIDGE_ENABLED` | `false` |
| `STOA_PLUGIN_SDK_ENABLED` | `false` |
| `STOA_PLUGIN_DIR` | unset (read directly when the plugin loader runs) |
| `STOA_IP_BLOCKLIST` | empty | CSV of IPs/CIDRs dropped before HTTP. |
| `STOA_IP_BLOCKLIST_FILE` | unset | One CIDR per line. |
| `STOA_TCP_RATE_LIMIT_PER_IP` | unset | Positive finite rate, or unset to disable. |
| `STOA_MEMORY_LIMIT_MB` | `512` | Backpressure at 80%. |
| `STOA_SNAPSHOT_ENABLED` | `false` | |
| `STOA_SNAPSHOT_MAX_COUNT` | `100` | |
| `STOA_SNAPSHOT_MAX_AGE_SECS` | `3600` | |
| `STOA_SNAPSHOT_BODY_MAX_BYTES` | `4096` | |
| `STOA_SNAPSHOT_EXTRA_PII_PATTERNS` | empty | |
| `STOA_EBPF_DAEMON_URL` | unset | Read directly. Unset → no eBPF client. |

### mTLS (`STOA_MTLS__*`)

Separate from `STOA_TRUSTED_PROXIES`. Empty `STOA_MTLS__TRUSTED_PROXIES` with
`STOA_MTLS__ENABLED=true` refuses to boot.

| Variable | Default |
| --- | --- |
| `STOA_MTLS__ENABLED` | `false` |
| `STOA_MTLS__REQUIRE_BINDING` | `true` |
| `STOA_MTLS__TRUSTED_PROXIES` | empty |
| `STOA_MTLS__ALLOWED_ISSUERS` | empty |
| `STOA_MTLS__REQUIRED_ROUTES` | empty |
| `STOA_MTLS__TENANT_FROM_DN` | `true` |
| `STOA_MTLS__HEADER_VERIFY` | `X-SSL-Client-Verify` |
| `STOA_MTLS__HEADER_FINGERPRINT` | `X-SSL-Client-Fingerprint` |
| `STOA_MTLS__HEADER_SUBJECT_DN` | `X-SSL-Client-S-DN` |
| `STOA_MTLS__HEADER_ISSUER_DN` | `X-SSL-Client-I-DN` |
| `STOA_MTLS__HEADER_SERIAL` | `X-SSL-Client-Serial` |
| `STOA_MTLS__HEADER_NOT_BEFORE` | `X-SSL-Client-NotBefore` |
| `STOA_MTLS__HEADER_NOT_AFTER` | `X-SSL-Client-NotAfter` |
| `STOA_MTLS__HEADER_CERT` | `X-SSL-Client-Cert` |

### DPoP and sender constraint

| Variable | Default |
| --- | --- |
| `STOA_DPOP__ENABLED` | `false` |
| `STOA_DPOP__REQUIRED` | `false` |
| `STOA_DPOP__MAX_AGE_SECS` | `300` |
| `STOA_DPOP__CLOCK_SKEW_SECS` | `30` |
| `STOA_DPOP__JTI_CACHE_TTL_SECS` | `600` |
| `STOA_DPOP__JTI_CACHE_MAX` | `100000` |
| `STOA_SENDER_CONSTRAINT__ENABLED` | `false` |
| `STOA_SENDER_CONSTRAINT__DPOP_REQUIRED` | `false` |
| `STOA_SENDER_CONSTRAINT__MTLS_REQUIRED` | `false` |

### Legacy env names (no `STOA_` prefix)

Accepted by the loader for older manifests: `PORT`, `HOST`, `JWT_SECRET`,
`KEYCLOAK_URL`, `KEYCLOAK_REALM`, `GITLAB_URL`, `GITLAB_TOKEN`,
`GITLAB_PROJECT_ID`, `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_CATALOG_REPO`,
`GITHUB_GITOPS_REPO`, `GITHUB_WEBHOOK_SECRET`, `GIT_PROVIDER`.

`ModeConfig::from_env` also recognises `STOA_MODE`, `STOA_SSE_KEEPALIVE`,
`STOA_SSE_KEEPALIVE_INTERVAL`, `STOA_MAX_SESSIONS`, `STOA_SESSION_TIMEOUT`,
`STOA_UPSTREAM_TYPE`, `STOA_USER_INFO_HEADER`, `STOA_TENANT_ID_HEADER`,
`STOA_TRANSFORM_REQUEST`, `STOA_TRANSFORM_RESPONSE`, `STOA_INJECT_HEADERS`,
`STOA_WEBSOCKET_PASSTHROUGH`, `STOA_CONNECTION_POOL_SIZE`, `STOA_UAC_OUTPUT_DIR`,
`STOA_AUTO_CREATE_MR`, `STOA_GITLAB_PROJECT`, `STOA_MIN_REQUESTS_FOR_UAC`, and
`STOA_ANALYSIS_WINDOW_HOURS`. The binary's startup path uses `Config::load`
(`STOA_GATEWAY_MODE`), not `ModeConfig::from_env`.

## Published-route JWT proof

A contract with `inboundAuth: jwt` (or a `jwt_validation` policy) requires a
Keycloak RS256 bearer on the REST route. No header → 401 with
`WWW-Authenticate`. Valid client-credentials token → proxied. Expired token →
401. A contract without that policy is unchanged. Audience check stays off.

```bash
STOA_PROOF_BIN=./stoa-gateway/target/debug/stoa-gateway deploy/standalone/jwt-proof.sh
```

The script prints status codes only.
