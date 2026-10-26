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

Detect, Discover, ApplyPolicy, RemovePolicy and InjectCredentials return a typed
`UnsupportedError` without side effects. Policy requests are rejected regardless
of policy type or configuration. Discovery is skipped in Envoy mode. Credential
and policy sync callers receive explicit errors if those operations are attempted.
