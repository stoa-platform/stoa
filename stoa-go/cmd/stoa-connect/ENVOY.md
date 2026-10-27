# Envoy mode

Select explicitly with `STOA_GATEWAY_TYPE=envoy`; automatic detection never
selects Envoy. ADS starts only in this mode and stops with the agent context.
The same server instance is used for route synchronization. No gateway admin
URL is required: the runtime supplies an internal target for the sync loops.

Configuration:

- `STOA_ENVOY_ADS_ADDR`: ADS bind address, default `127.0.0.1:18000`.
  Only loopback IP literals are accepted, including when overridden.
- `STOA_ENVOY_NODE_URI`: required URI SAN of the authorized Envoy client.
- `STOA_ENVOY_TLS_CERT`, `STOA_ENVOY_TLS_KEY`: server certificate and key paths.
- `STOA_ENVOY_CLIENT_CA`: client trust bundle path. Mutual TLS is mandatory.
  Clients must have exactly one URI SAN in a verified certificate chain.
  The verified URI determines the snapshot key; declared node IDs are ignored.
- `STOA_ENVOY_LISTENER_PORT`: required generated data listener port (loopback).
- `STOA_ENVOY_AUTH_ADDR`: required external authorization service host:port.
  Authorization fails closed; its timeout is one second.

Activated routes are published as a complete snapshot and wait up to five
seconds for CDS, LDS and RDS ACKs. NACKs and deadlines return deployment errors.
Without `path_prefix`, the path is `/apis/{api_id}`. SSE payloads use
`api_catalog_id` as the route resource ID when `id` is absent.

SSE publications merge into the last acknowledged complete route table. Explicit
deletion tombstones may remove the final route; unexplained route loss is rejected.
The first SSE heartbeat certifies subscription, then the agent reconciles the full
CP deployment config, including deletion tombstones and generations. Older queued
events cannot restore a removed generation. CP retains tombstones until `removed`.

Policy inventory must include `scope`, `api_catalog_ids`, `tenant_id` and
`applicable`, derived from enabled CP bindings. Empty API bindings never broaden
to gateway scope. Display names do not identify routes or policies. The agent
atomically reconciles the complete applicable enabled set; disappearance, disabled
bindings and disabled policies remove previously applied configurations. Missing
attribution, unsupported types, conflicting same-type rules on a route, unknown
API targets, NACKs and timeouts fail explicitly and retain acknowledged state.

Translated v1 policies (no functional parity claim):

- `cors`: the six contract keys, emitted per route using the CORS filter.
  Method-constrained routes also accept OPTIONS for preflight; ext_authz still
  runs before CORS and may deny the preflight without contacting the upstream.
- `rate_limit`: `maxRequests` and `intervalSeconds`, as a local token bucket per
  route and Envoy process. This is not a distributed or fixed-window quota.
- `ip_filter`: allow/deny against the direct peer address, without trusting
  forwarded address headers; CIDR and single-address entries are supported.

Scopes `gateway` and `tenant` expand onto matching routes; API scope uses exact
catalogue resource IDs. Same-type rules on overlapping scopes are rejected rather
than implicitly combined or overridden by priority. Policies also survive route
resynchronization. An API policy arriving before its route fails and is retried
on the next config cycle. A rejected inventory prevents partial application of
the batch. Normal policy polling remains the recovery path for dropped SSE events.

`jwt_validation` (including deprecated `jwt`), `logging`, `caching`, `transform`
and OIDC policies remain explicitly unsupported by this translator. STOA's real
authorization service is a separate prerequisite; the Envoy ext_authz filter
remains fail-closed and precedes CORS, local rate limiting, RBAC and routing.

Detect, Discover and InjectCredentials still return typed `UnsupportedError`.
Discovery is skipped in Envoy mode; credential injection fails explicitly.
