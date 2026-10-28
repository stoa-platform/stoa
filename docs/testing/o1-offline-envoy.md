# Offline O1 acceptance harness

This opt-in test exercises the production CP deployment HTTP router, real
SQLAlchemy repositories, targeted event bus and SSE endpoint, the Go Agent and
adapters, an mTLS ADS server, a real Envoy process and an independent gRPC
`Authorization.Check` witness. It does not use the pending Rust adapter.

Prerequisites already present locally: Python CP runtime/dev dependencies, Go
with cached modules, Docker, and the pinned Envoy image below. The test does not
pull images, download Go dependencies, use Keycloak, or contact a deployment.
The CP listens locally; the disposable container reaches it through Docker's
host bridge. ADS, Envoy, the authorization witness and upstream share that
container; no container ports are published. Temporary certificates are generated
per execution. Envoy's admin interface uses a temporary Unix socket.

```sh
cd control-plane-api
O1_RUN_ENVOY=1 O1_EVIDENCE_DIR=/tmp/stoa-o1-evidence \
  python3 -m pytest tests/test_o1_offline_envoy.py -q --no-cov
```

Without `O1_RUN_ENVOY=1`, ordinary unit-test runs skip this container test.
The image is `envoyproxy/envoy@sha256:29d778ba078e0404d18fa45ffb834c062071b0f81dc0a6a41501ce8e23a0059f`.
The fixture detects its local architecture and cross-compiles the Go test binary
with `GOPROXY=off`, `GOSUMDB=off` and `CGO_ENABLED=0`. A missing image, module or
tool fails explicitly. For successive runs on Docker Desktop, use pytest's
default unique temporary directory rather than recycling a deleted bind mount.

The route harness belongs to CAB-2256; the optional `o1_policies_test.go` hook
adds CAB-2280 acceptance checks. Removing that file leaves the route harness and
authorization witness independent of the policy implementation. Python fixture
routes under `/o1` only seed catalog/policy rows, collect policy ACKs and inject an
unexpected empty config. Publication, removal, CP config, SSE and route ACKs use
the production routes and repositories. Operator authentication alone is a test
dependency override granting a synthetic cpi-admin role; the gateway key is a
fixture value. The CP database is SQLite, not PostgreSQL.

Assertions:

- Ten sequential publications on an already connected Envoy. Each latency starts
  when the CP 2xx response is received and stops when the route is in the accepted
  config_dump and a request through Envoy receives the upstream's 200/header.
  A monotonic clock measures durations; every result must be strictly below five
  seconds. Median and maximum are recorded, and CP `synced` ACKs are checked.
- Route count never decreases during publication polls. A CP empty-response
  fault must preserve the snapshot. Only explicit deletion tombstones may remove
  routes, including the final route; removed paths return 404 and CP tombstones
  disappear only after removal ACKs.
- A foreign gateway publication leaves version and route count unchanged during
  five seconds of observation. During an SSE outage the old snapshot serves
  traffic; a fresh agent/adapter reconstructs the table and a missed publication
  within five seconds of restart.
- With the policy hook: actual CORS response headers, token-bucket 429 behavior,
  direct-address allow/deny behavior, API isolation, update/removal and an
  unsupported inventory refused without publication. The inventory records only
  IDs, types, scopes and targets for policies observed enabled and applicable;
  it is a history of the scenario, not a production inventory or a claim that
  all three were enabled simultaneously.
- Real gRPC Check calls precede routing. Business denial, gRPC failure and timeout
  return 403 without reaching the upstream. The policy hook additionally checks
  that CORS preflight cannot bypass an ext_authz denial.

`o1-result.json` records the candidate SHA, image digest, platform, Paris start/end
times, ten measurements, lifecycle timings, inventory and verdict. `o1-envoy.log`
records the test trace; failed attempts save an address-masked diagnostic log.
Raw config_dump and temporary key material are not copied into evidence.

Limits: count checks sample every 100 ms; they do not establish uninterrupted
behavior between samples. A gRPC witness validates the integration contract,
not STOA JWT/business authorization. TLS uses the real ADS server and verified
client certificate identity, while the agent is invoked from its Go package
rather than the CLI registration launcher. The normal CLI mTLS tests remain
part of `go test -race ./...`. No production-active policy list is inferred.

On Docker Engine (Linux), `host.docker.internal:host-gateway` resolves to the
bridge gateway, not to the host loopback: set `O1_CP_BIND` to that gateway address
(`docker network inspect bridge`) so the CP fixture listens where the container
can reach it. The default, `localhost`, suits Docker Desktop.

For a future manual Linux CI recipe, provision the same pinned image and cached
dependencies before this offline command, then archive the evidence directory
and candidate SHA. Use `workflow_dispatch`, never a pull-request E2E trigger.
That CI execution and independent acceptance review remain required before
closing the ticket; this local run is not a CI result.
