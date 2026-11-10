# Standalone gateway

Run `stoa-gateway` without control-plane-api. Contracts come from stoactl
through `POST /admin/contracts`. This directory is the k3s layout for that
mode: namespace `stoa`, ingress-nginx, node `worker-3`.

Public calls move from APISIX to this process only when you run the switch
script. Root apply does not touch Service `gateway` or the public Ingress.

`jwt-proof.sh` is the published-route JWT check (Keycloak plus nginx).

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

## Apply, switch, rollback

The node selector is `kubernetes.io/hostname=worker-3` (the k3s node name).
Confirm it with `kubectl get nodes` before Friday. Namespace is `stoa`.

```bash
kubectl -n stoa create secret generic stoa-gateway-admin \
  --from-literal=STOA_ADMIN_API_TOKEN="$(openssl rand -hex 32)"
kubectl apply -k deploy/standalone
```

That installs one replica, the ConfigMap, and the in-cluster Services
`stoa-gateway` and `stoa-gateway-admin`. There is no PodDisruptionBudget.
It does not create or patch Service `gateway` and it does not create an
Ingress. APISIX keeps `api.gostoa.dev`.

`secret.yaml` is a template (`REPLACE_FROM_VAULT`). It is not in
`kustomization.yaml`. The Deployment reads `STOA_ADMIN_API_TOKEN` from Secret
`stoa-gateway-admin`, not from the ConfigMap.

`STOA_ENVIRONMENT` is `dev`. `prod` and `staging` refuse to boot unless
`STOA_POLICY_PATH` points at an existing Rego file (`stoa-gateway/policies/default.rego`
is not in the image).

### Why the switch is not `kubectl apply -k`

Service `gateway` today fronts APISIX. Its port is 9080. This process listens
on 8080. `kubectl apply` strategic-merges `spec.selector`, so a manifest whose
selector is only `app: stoa-gateway` keeps whatever APISIX keys are already
there. The Service then matches no pods and `api.gostoa.dev` returns 502.
The same merge would not delete a Prefix `/` Ingress path, so `/admin/contracts`
would stay public.

`switch.py` reads the live objects and `kubectl replace`s them. The first
switch saves the live selector, the port-9080 targetPort, and the
`api.gostoa.dev` paths into ConfigMap `stoa/stoa-gateway-switch-backup`.

Before Friday, read the live objects and stop if the host is not
`api.gostoa.dev` or there is no port 9080:

```bash
kubectl -n stoa get svc gateway -o yaml
kubectl -n stoa get ingress -o yaml
```

Switch (the deployment must already exist; `/ready` stays 503 until Keycloak answers):

```bash
deploy/standalone/overlays/use-stoa-gateway/switch.sh
```

The script stops before touching Service `gateway` unless all of these hold:

- `worker-3` has `stoa-gateway:standalone` in the k3s containerd namespace,
  and its `org.opencontainers.image.revision` label equals
  `deploy/standalone/IMAGE-REVISION` (override with `STOA_EXPECTED_REVISION`,
  SSH host with `STOA_NODE_SSH`)
- `sudo systemctl start stoa-pvc-backup.service` on that node exits 0.
  The oneshot finishes before the ConfigMap is patched. Confirm the new
  archive with `sudo journalctl -u stoa-pvc-backup -n 20 --no-pager`.
- `STOA_TRUSTED_PROXIES` can be set to the Running ingress-nginx pod IPs.
  The ConfigMap in git keeps the sentinel
  `REPLACE_WITH_INGRESS_NGINX_POD_IPS`. The script resolves the pod IPs,
  writes those addresses only (never a node `/24`), reads the ConfigMap
  back, and exits if the sentinel is still there. It then restarts the
  deployment so the process loads the new value. `envFrom` is not live.

kubectl is `kubectl-stoa` when that binary is on `PATH`. Override with
`KUBECTL` or `K` (the operator value is `K=~/stoa-deploy-bin/kubectl-stoa`).
`KUBECTL` wins over `K`.

It then sets selector `app: stoa-gateway`, keeps Service port 9080, sets
`targetPort` 8080, and replaces the `api.gostoa.dev` paths with Prefix `/apis`
only. Other hosts on the same Ingress are left as they are.

A later `kubectl apply -k deploy/standalone` puts the sentinel back into the
ConfigMap object. The running process keeps the IPs it started with until
the next restart. Run `switch.sh` again before that restart if the
ingress-nginx pod IP changed. Do not put a node `/24` in the list.

The public Ingress is `stoa-api`, not a new Ingress. Switch narrows its
`api.gostoa.dev` rule to Prefix `/apis` only. `/admin`, `/metrics`, `/mcp`,
`/oauth/register`, and `/v1/messages` are not on that rule.
`deploy/standalone/ingress.yaml` is not in this tree. Do not apply one.

Rollback is versioned:

```bash
deploy/standalone/overlays/use-apisix/rollback.sh
```

It puts Service `gateway` back to selector `app: apisix` and targetPort
`9080`, and restores the `stoa-api` paths saved at switch time. NotFound
on the backup ConfigMap is the only read result treated as "no backup".
Any other read error exits before Service `gateway` or Ingress `stoa-api`
is replaced. With no backup it applies the baseline in
`overlays/use-apisix/stoa-api.yaml`:
Prefix `/` to `gateway:9080`. That rule matches
`/demo-customer-referential/v1/customers/C-1001`. APISIX on that port
answers 401 to an anonymous caller. The STOA Prefix `/apis` rule does not
match that URL. `switch.py --self-test` checks the match and the 401
without calling the cluster. A later
`kubectl apply -k deploy/standalone` does not list Service `gateway`,
Ingress `stoa-api`, or the backup ConfigMap, so it cannot undo the rollback
or repeat the switch. `desired-service.yaml` and `desired-ingress.yaml` are
not kustomize resources. `kubectl apply` is the wrong tool for the selector:
it merges map keys and the Service then matches nothing.

## Public URLs

After the switch, published operations are:

```text
https://api.gostoa.dev/apis/<tenant>/<name>/<endpoint>
https://api.gostoa.dev/apis/demo/live-api/ping
```

`/mcp`, `/.well-known`, `/oauth`, `/health`, and `/ready` are not on the
`api.gostoa.dev` Ingress. The MCP endpoint has its own host, see "Public
MCP" below. Admin stays on the ClusterIP, which has no Ingress rule:

```text
http://stoa-gateway-admin.stoa.svc:8080/admin/contracts
```

There is no `allowUnauthenticatedREST` flag in this repo. With
`STOA_CONTROL_PLANE_URL` unset, `POST /admin/contracts` returns 400 and
stores no route unless the contract sets `inboundAuth` to `jwt` (or a
`jwt_validation` policy). A route that was already in memory is removed.
With a control plane URL set, a contract without that policy is still
published open. `inboundAuth` values other than `jwt`, `bearer`, `oauth2`,
`oidc`, or `client_credentials` are rejected (400), as is a field whose
name looks like `inboundAuth` (`InboundAuth`, `inboundAut`). Other unknown
fields are still ignored.

The process returns 400 for an ambiguous path (`..`, `%2e`, `%2f`, `//`) and
404 for any other path when `X-Forwarded-For` or `X-Forwarded-Host` is set,
unless the path is `/apis` or `/apis/...`. ingress-nginx sets both headers.
A direct ClusterIP or `kubectl port-forward` call does not, so kubelet probes
and in-cluster stoactl still reach `/health` and `/admin`. A proxied call to
`/admin`, `/metrics`, `/mcp`, `/oauth/register`, or `/v1/messages` is 404,
not 401. `STOA_PUBLIC_MCP_ENABLED=true` takes `/mcp` out of that list and
nothing else.

## Public MCP

`STOA_PUBLIC_MCP_ENABLED` is `false` in the binary and `true` in this
ConfigMap. When it is set, a request that carries `X-Forwarded-For` or
`X-Forwarded-Host` is also delivered for:

```text
/mcp and /mcp/... (except /mcp/health)
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-protected-resource/mcp/sse
/.well-known/oauth-authorization-server
/.well-known/openid-configuration
/health  /health/ready  /health/live  /ready
```

The list is exact. `/admin`, `/metrics`, `/mcp/health` (it reports session
and tool counts), `/oauth/token`, `/oauth/par`, `/oauth/register`,
`/v1/messages`, `/a2a`, `/.well-known/agent.json` and any other path are
still 404 behind a proxy, with or without a valid admin bearer. An ambiguous path (`/mcp/../admin`, `/mcp/%2e%2e/metrics`) is still
400. A direct ClusterIP or port-forward call is not affected.

Authentication on the MCP transports:

| Request | Without an accepted bearer |
| --- | --- |
| `GET /mcp`, `GET /mcp/capabilities` | 200, static discovery |
| `POST /mcp`, `POST /mcp/sse`: `initialize`, `ping`, `notifications/initialized`, `notifications/cancelled` | answered |
| `POST /mcp`, `POST /mcp/sse`: any other method, alone or in a batch | 401 (per-element error in a batch) |
| `GET /mcp/sse`, `DELETE /mcp/sse` | 401 |
| `GET /mcp/ws` (only if `STOA_WEBSOCKET_ENABLED`) | 401 before the upgrade |
| REST routes under `/mcp/` (`/mcp/tools/...`, `/mcp/v1/tools`, `/mcp/events`, ...) | 401 |

An accepted bearer is a JWT the validator verifies: issuer
`${STOA_KEYCLOAK_URL}/realms/${STOA_KEYCLOAK_REALM}`, audience
`STOA_JWT_AUDIENCE`. A header with another scheme (`Basic`, ...) or an
empty bearer is anonymous. A bearer that is presented and rejected is 401
whatever the method, and refuses a whole batch. With a validator the tenant
comes from the token (or `default`), not from `X-Tenant-ID`, on the JSON-RPC
transports and on the REST routes; an anonymous caller is in `default`. A
session that belongs to a tenant is used, reopened or closed only by that
tenant (`Session tenant mismatch` otherwise). A session opened anonymously
stays usable by the client that holds its id.

Without `STOA_KEYCLOAK_URL` there is no validator: a bearer is then taken as
is and the REST gate lets every request through. That is a development
mode. `Config::validate` refuses to boot with the option set in that case,
and the router keeps the surface closed if a state is built without that
check.

Not covered here: `GET /mcp/events` takes its `tenant_id` from the query for
any authenticated caller, and `resources/list` is not filtered by tenant.
The standalone deployment has one tenant and no event source
(`STOA_KAFKA_ENABLED=false`).

### Sign-in for MCP clients

A 401 on an MCP route carries
`WWW-Authenticate: Bearer resource_metadata="<STOA_GATEWAY_EXTERNAL_URL>/.well-known/oauth-protected-resource/mcp"`
(`.../mcp/sse` on the SSE endpoint). The URL is absolute: a client requests
it as is. Each MCP endpoint has its own document (RFC 9728 §3.1) whose
`resource` is the endpoint URL, `<STOA_GATEWAY_EXTERNAL_URL>/mcp` or
`.../mcp/sse`: a client compares that value with the URL it was configured
with (Claude asks for the two to be equal, path included; the MCP SDK also
accepts a parent of the URL). `STOA_GATEWAY_EXTERNAL_URL` must therefore be the host
MCP clients use (`https://mcp.gostoa.dev` in this ConfigMap), and the URL
to give a client is `https://mcp.gostoa.dev/mcp`. Boot is refused when the
value is not an absolute `http(s)` URL without query, fragment or quote.
`/.well-known/oauth-protected-resource` without a path is still served,
with the base URL as `resource`.

`authorization_servers` in those documents is
`STOA_OAUTH_AUTHORIZATION_SERVERS`, here the realm,
`https://auth.gostoa.dev/realms/stoa`. A client fetches the realm's own
metadata (`<issuer>/.well-known/openid-configuration`), checks that its
`issuer` is the URL it was given, sends the browser to the realm and
exchanges the code at the realm's token endpoint. The gateway is not on
that path: it only validates the bearer it then receives (issuer, and
`aud` = `STOA_JWT_AUDIENCE`). `scopes_supported` is
`STOA_OAUTH_SCOPES_SUPPORTED`: list only scopes the realm defines, a
client asks for what it reads there.

The client the user signs in with is a public client the realm defines,
`stoa-mcp-client` (PKCE S256 required, consent asked, an audience mapper
for `stoa-gateway`, no secret; stoa-v2 `deploy/k3s/keycloak/mcp-client.sh`).
Its id is given to the MCP client by hand. The realm must advertise a token
endpoint a client can reach: on 2026-11-10 it advertised
`https://auth.gostoa.dev:80/...` for requests that came through the tunnel
on the plain HTTP port of ingress-nginx; the tunnel route of
`auth.gostoa.dev` has to use the TLS port (stoa-labs).

Without `STOA_OAUTH_AUTHORIZATION_SERVERS` the documents name the gateway
itself. Its own `/.well-known/oauth-authorization-server` and
`/.well-known/openid-configuration` carry the realm as `issuer` and the
gateway's OAuth proxy (`/oauth/token`, `/oauth/par`, `/oauth/register`) as
endpoints. That suits a client that does not compare the issuer with the
URL it was given (the MCP SDK does, RFC 8414 §3.3, and stops there), and
it needs `/oauth/...` to be delivered to that client. Here `/oauth/...` is
404 behind a proxy, dynamic client registration included. Should
registration be opened one day: the proxy forwards a registration to the
realm (it only drops `scope`), so the realm's client registration policies must first
rule out a self-registered confidential client with the
`client_credentials` grant, which would be a token with no user.

Routing is outside this tree: DNS `mcp.gostoa.dev` and the tunnel route
are in stoa-labs (`deploy/bootstrap/edge/cloudflared/config.yaml`), the
Ingress `stoa-mcp` is in stoa-v2 (`deploy/k3s/ingress-mcp.yaml`) and sends
only `/mcp`, `/.well-known`, `/health` and `/ready` to Service
`stoa-gateway`.

An anonymous `POST` without a session id creates an MCP session kept for
`STOA_MCP_SESSION_TTL_MINUTES`. The session map has no size cap. The memory
backpressure (`STOA_MEMORY_LIMIT_MB`) samples process memory and answers
503 above its line; it is not a session limit. The bound for the public
host is the rate limit on the Ingress (`limit-rps`, `limit-connections`).

Unset or empty `STOA_ADMIN_API_TOKEN` makes a direct `/admin` call return 503.
A missing or wrong bearer returns 401. There is no default token.

## MCP tools from published contracts

Each endpoint of a contract published with `POST /admin/contracts` becomes
one MCP tool. `tools_generated` in the response is the number of tools the
registry holds after the publish: a tool the registry refuses (an
`input_schema` whose `type` is not `object`, for example) is left out and
logged.

- Name: the endpoint's `llm.tool_name`, as given. Without it,
  `<tenant>_<name>_<operation_id>`, or the endpoint's position in
  `endpoints` (from 0) when it has no `operation_id`. Any character outside
  `A-Z a-z 0-9 _ -` becomes `_`. A name longer than 64 characters is cut and
  ends with `_` and 8 hex characters of a SHA-256 of the full name. Images
  before this change named these tools `uac:<tenant>:<name>:<operation_id>`,
  or `uac:<tenant>:<name>:<name>-<index>` without an `operation_id`.
- Method: the tool sends the first entry of `methods` only. An endpoint with
  `methods: [GET, POST]` gives one tool that calls GET; POST is served by
  the REST route only.
- Path parameters: `backend_url` is the upstream URL of the static part of
  the path, up to the first `{param}` segment. For `/customers/{id}` it is
  `https://backend.example/customers/`, the REST route is
  `/apis/<tenant>/<name>/customers/`, and the tool takes a required string
  argument `id`: `{"id": "C-1001"}` calls
  `https://backend.example/customers/C-1001`. A given `input_schema` keeps
  its properties and gets the missing path parameters. The other arguments
  go as query string (GET, DELETE) or JSON body (POST, PUT, PATCH).
- Path parameter values: a value that is empty, `.` or `..`, or that
  contains `/`, `\` or a control character is refused before any request
  is sent (invalid arguments; the error names the parameter, not the
  value). `..` would otherwise call the parent of the backend path with the
  caller's bearer, and an empty value the collection. Other values are
  percent-encoded.
- Refused paths and `backend_url`: the publish returns 400
  (`"status": "rejected"`, the message names `endpoints[<i>]` and its path)
  when a `backend_url` contains `{` or `}`, a path does not start with `/`,
  braces are unmatched or empty (`/customers/{id`, `/a/{}`), or a parameter
  is not a whole segment (`/a{id}`, `/files/f-{id}`). The REST binder
  refuses it before changing a route or a tool; the restore after a refusal
  (below) still applies.
- REST routes and methods: a route is a prefix and serves every path under
  it. Endpoints whose static part is the same share one route, and the
  methods of all of them are merged on it. `GET /customers/{id}` and
  `DELETE /customers/{id}/sessions/{sid}` both give
  `/apis/<tenant>/<name>/customers/`, which then allows GET and DELETE:
  `DELETE /apis/<tenant>/<name>/customers/C-1` reaches the backend
  (`https://backend.example/customers/C-1`) although the contract declares
  no DELETE on `/customers/{id}`. Authentication is not widened: the route
  keeps the contract's JWT policy and audience, for every method. Two
  endpoints with the same static part and different `backend_url` are
  refused (400).
- Segment boundary: a route serves the path equal to its prefix and the
  paths under it, not a longer segment. `/apis/<tenant>/<name>/customers`
  serves `.../customers`, `.../customers/` and `.../customers/C-1`, not
  `.../customers-archive/1` or `.../customersX` (404 unless another route
  matches). The longest matching prefix wins.
- Upstream URL: the rest of the request path after the route prefix
  (percent-decoded) is appended to `backend_url` without its trailing `/`,
  with a `/` in front when it has none, so it cannot change the backend
  host. It is not otherwise rewritten (`//` stays). The query is kept.
- Tenant: `tools/list` shows a contract tool only to a caller of the
  contract's tenant, and `tools/call` refuses the others. The caller's
  tenant is the token's `tenant` claim, else its first realm role
  `tenant-<x>`, else `default`.
- Scope, with the built-in policy (no `STOA_POLICY_PATH`): the tool's
  action comes from `llm.side_effects` when the endpoint has `llm`: `none`
  or `read` make a read tool whatever the method, a POST or DELETE endpoint
  included; `destructive` a delete tool; `write` the action of the method.
  Without `llm`, from the first method: POST create, PUT and PATCH update,
  DELETE delete, GET and any other method read. A read tool needs
  `stoa:read` in the token's `scope`; `stoa:execute`, `stoa:admin` or the
  realm role `cpi-admin` also pass. On `POST /mcp` a token with no scope at
  all counts as `stoa:read`. Create, update and delete tools need
  `stoa:write` (or `stoa:admin`, or `cpi-admin`).
- Call: the gateway calls the backend directly with the caller's bearer
  (`Authorization: Bearer <token>`). It does not go through the `/apis`
  route, so `inboundAuthAudience` is not checked on this path; the token was
  checked against `STOA_JWT_AUDIENCE` on `/mcp`.
- Republishing a contract replaces its tools: those of removed endpoints
  disappear. `DELETE /admin/contracts/<tenant>:<name>` removes them, whatever
  their names. A name held by another contract or by a tool that is not
  from this contract, or produced by two endpoints, is refused with 400.
- After a refused publish (400), the previous version's routes and tools
  are back in place when the response is sent, not during the whole
  request. The handler binds the previous version again: its REST routes
  are removed and re-added, and a request in that short window gets 404.
  A refusal by the REST binder (a path, a `backend_url`, a prefix with two
  backends) comes before any change of its own. A refusal by the MCP binder
  (a tool name) comes after the REST binder has installed the refused
  version's routes: they serve requests until the previous routes replace
  them, or, for a contract not published before, until they are removed.
- One at a time: contract publications and deletions run one after the
  other. A `POST` or `DELETE /admin/contracts` waits until the one in
  progress has answered.
- Without a control plane and with `STOA_NATIVE_TOOLS_ENABLED=false` (this
  ConfigMap), no `stoa_*` platform tool is registered at startup. Three
  calls still start a tool discovery for the caller's tenant:
  `GET /mcp/v1/tools` and `POST /mcp/tools/list` in the background when the
  tenant's list is older than `STOA_TOOL_REFRESH_TTL_SECS` (300), and
  `POST /mcp/tools/call` (or `POST /mcp/v1/tools/invoke`) on an unknown
  tool, inline, when the tenant was never loaded. The discovery calls the
  control-plane client, whose URL is `http://localhost:8000` when
  `STOA_CONTROL_PLANE_URL` is unset. Nothing listens there in this pod: the
  call fails, the tenant is marked loaded, and no tool is added. A process
  answering on that address would have its tools registered as relay
  tools. `tools/list` on `POST /mcp` starts no discovery.
- Routes and tools are process memory. After a restart `tools/list` has no
  contract tool until the publisher posts the contracts again (see
  "Republish after a restart").

## Resilience

One replica, no PodDisruptionBudget, `nodeSelector` `worker-3`. Memory
request 256Mi, limit 1Gi. The v1 gateway was OOM-killed at 512Mi.
`STOA_MEMORY_LIMIT_MB=768` is the in-process backpressure line, under that
cgroup limit.

Published routes and their JWT policies live in the process. `POST
/admin/contracts` reaches whichever pod receives the connection. Two
replicas would answer about half of the public calls with 404, and one
pod could still be serving a route the other pod had already replaced.
More than one replica waits on a later change: the publish has to reach
every pod, or the routes have to live in shared state. Until then the
Deployment stays at `replicas: 1`. A restart drops every route until
stoactl publishes again, and `GET /apis/<tenant>/<name>/...` is 404 until
that publish lands. A rollout of this single pod has a gap with no
ready endpoint.

## Republish after a restart

Routes and JWT policies are process memory. There is no disk replay.
stoactl (stoa-v2, not in this repository) is the publisher: the same
`POST /admin/contracts` as the first publish, with the admin bearer,
`inboundAuth: jwt`, and an audience. The target is the ClusterIP, not
the public Ingress:

```text
http://stoa-gateway-admin.stoa.svc:8080/admin/contracts
```

`deploy/standalone/republish-contracts.sh` prints that call for each
contract JSON file. It does not run kubectl or ssh. `--post` sends the
body only when `STOA_ADMIN_API_TOKEN` and `STOA_GATEWAY_ADMIN_URL` are
set. A file without `inboundAuth` is refused before any request.
`POST /admin/apis`, `POST /admin/policies`, and `DELETE /admin/policies` return 403 in standalone.
`POST /admin/apis` stores a trusted route with no JWT policy.
`POST /admin/policies` can replace `jwt:<route>` and drop its audience.
`DELETE /admin/policies` removes a policy and leaves the route open.

```bash
deploy/standalone/republish-contracts.sh contracts/*.json
deploy/standalone/republish-contracts.sh --self-test
```

The audit spool is only opened from tests (`AuditSpool::open`). Startup does
not create it. The only volume is an `emptyDir` at `/tmp` because the root
filesystem is read-only. There is no PVC.

## Trusted proxies and network policy

`STOA_TRUSTED_PROXIES` (not `STOA_MTLS__TRUSTED_PROXIES`) is the allow list for
`X-Forwarded-For` and `X-Forwarded-Proto`. The TCP peer must sit in the list.
On this cluster that peer is an ingress-nginx pod. Cloudflare ranges are not
in the list: the tunnel never presents a Cloudflare address as the TCP peer.
`10.42.0.0/16` is not in the list either: other namespaces share that CIDR.

The ConfigMap ships the sentinel `REPLACE_WITH_INGRESS_NGINX_POD_IPS`. That
string is not a CIDR, so no peer is trusted and a spoofed
`X-Forwarded-For` is ignored. `switch.sh` replaces it, at switch time, with
the Running pod IPs from
`kubectl -n ingress-nginx get pods -l app.kubernetes.io/name=ingress-nginx`.
It keeps `status.podIP` only for a Running pod and only when that address
has no slash, then patches ConfigMap `stoa-gateway` key
`STOA_TRUSTED_PROXIES` with those bare addresses. It reads the key back.
`assert_host_only` accepts a bare address and a prefix whose length is the
maximum for that family (`/32` or `/128`). It refuses the sentinel, an empty
value, and any wider prefix, including a node `/24`. That refusal is a
preflight error: Service `gateway` and Ingress `stoa-api` stay on APISIX.
`switch.py --self-test` covers the host prefix and the wider prefixes with
the fixture address already in the script. At request time each entry is a
CIDR: a host prefix contains only that one address.

`networkpolicy.yaml` (`stoa-gateway-ingress`) allows TCP 8080 only from
ingress-nginx pods and from the two pods in `stoa` that call the admin API
with the admin token: the reconciler (`app.kubernetes.io/name=reconciler`)
and the console (`app.kubernetes.io/name=console`,
`app.kubernetes.io/part-of=stoa`). In-cluster stoactl runs in one of those
two pods; from anywhere else, use `kubectl port-forward`. Any other pod
calling the Service should time out, in `stoa` as in `default`. Node-local
traffic (kubelet probes, a host-network pod on the node) is not filtered.

The policy filters a port, not a path. A pod it names reaches the whole
listener, the paths that are 404 behind the proxy included, and the admin
token it holds decides what it may do there: there is one admin token and
it has no scopes. The console UI has no login of its own, so whoever
reaches that UI drives the admin calls the console makes. Give the console
pod an ingress policy that only admits the ingress controller.

## Image

No registry image exists for this build. `ghcr.io/stoa-platform/stoa-gateway`
is not updated from this PR. The Deployment uses `stoa-gateway:standalone`
with `imagePullPolicy: Never` (a reschedule without a local import fails
closed instead of pulling `docker.io/library/stoa-gateway`). Build from the
git SHA you are about to import. `FEATURES` is empty: no Pingora, Kafka, or
Kubernetes watcher. The build is `cargo chef cook --locked` and
`cargo auditable build --release --locked`. The binary is not stripped:
`strip` removes the `.dep-v0` section Trivy uses to see Rust crates. The
image label `org.opencontainers.image.revision` is that SHA.

```bash
deploy/standalone/build-image.sh
```

The script writes `stoa-gateway-standalone.tar`, its sha256, a CycloneDX
SBOM that must list Rust crates (including `quick-xml`), the Trivy HIGH
table, and `IMAGE-REVISION` (the SHA `switch.sh` requires on worker-3). It
exits if any CRITICAL finding is reported. `deploy/standalone/IMAGE-TRIAGE.md`
is where each HIGH is accepted or blocked in writing. `quick-xml` 0.39.4
HIGH is accepted only while no SOAP contract is published
(`STOA_SOAP_PROXY_ENABLED` and `STOA_SOAP_BRIDGE_ENABLED` stay false).
>= 0.41.0 avant tout câblage SOAP. Import is a separate step, on
worker-3, and this script does not run it:

```bash
docker save stoa-gateway:standalone | ssh worker-3 'sudo k3s ctr -n k8s.io images import -'
```

The Dockerfile is the cargo-chef build in `stoa-gateway/Dockerfile`
(builder `rust:1.93-bookworm`). `build-image.sh` builds its
`runtime-distroless` stage: `gcr.io/distroless/cc-debian13` pinned by digest,
user `1000:1000`, the binary and nothing to run beside it (no shell, no
package manager, no curl, no `HEALTHCHECK`; the probes are the Deployment's
HTTP probes). The script refuses an image that carries a shell or curl.
`kubectl exec` into the pod therefore has nothing to start: debug from
outside (logs, the probes, a debug container). The Dockerfile's default
target is still the Debian stage, for compose, Tilt and the e2e tests, whose
healthchecks run curl in the container; that stage is not deployed here.
`stoa-gateway/.dockerignore` excludes `target/`
so the context is not the local debug build. The image in service since
2026-11-10 is revision `ae6d3b868b399c21a05680268b7a6fdea48b50b7` (`IMAGE-REVISION`),
the first on the distroless runtime.
Tar sha256 `76ca7d83d57d93831d35387535782c9daebffa158ad54a54cc4fe7621ebd5fcf`.
A later docs commit does not change that binary. The label equals that
revision; `git diff ae6d3b868b399c21a05680268b7a6fdea48b50b7 HEAD -- stoa-gateway/`
is empty. The gateway is the one of revision
`36c4c3f934dd709c53e9f270845458b077741743`, the last image on the Debian
runtime: only the runtime stage differs. It adds, to the image of 2026-10-21 (revision
`6d23399e4d1a1f4c54a03122640c0469c8b4829c`), the opt-in public MCP surface
with the transport authentication ("Public MCP" above), tokio 1.54.1,
the sign-in metadata for MCP clients ("Sign-in for MCP clients") and the
distroless runtime.

Each import replaces the `standalone` tag on worker-3. Tag the image in
service first, so a rollback is a retag and a restart, with no rebuild:

```bash
ssh worker-3 'sudo k3s ctr -n k8s.io images tag docker.io/library/stoa-gateway:standalone docker.io/library/stoa-gateway:standalone-prev-<short sha>'
```

worker-3 holds `standalone-prev-36c4c3f9` (the third build of 2026-11-10: the
same gateway on the Debian runtime, so going back to it changes nothing for
a client), `standalone-prev-4e84fae7` (the second build),
`standalone-prev-c2e40501` (the first one, tokio 1.54.0) and
`standalone-prev-6d23399e` (2026-10-21). The second and the first build do not read
`STOA_OAUTH_AUTHORIZATION_SERVERS` nor `STOA_OAUTH_SCOPES_SUPPORTED`: with
them the 401 challenge is relative again and the documents name the
gateway, so an MCP client cannot sign in. The last one
has neither the public MCP option nor the transport authentication: with
it the MCP host answers 404 again, whatever the ConfigMap says. An
earlier local image id
`sha256:a8257c8f10341845343c72599aefc87b23a0f52bf38e14136eea4a6641a029fb`
does not contain audience enforcement, the path guard, or the admin proxy deny.
Do not import it.

After an import, `python3 deploy/standalone/switch.py preflight` is the
restart: it confirms the revision on worker-3, runs the volume backup,
writes the ingress-nginx pod IPs into `STOA_TRUSTED_PROXIES` and restarts
the Deployment. It does not touch Service `gateway` or Ingress `stoa-api`.
On 2026-11-10 its image check did not pass on this node before the fix in
`image_revision_on_node`, and the process that had been running since
2026-10-21 still had the sentinel.

`build-image.sh` builds for the host architecture. On an arm64 host, set
`DOCKER_DEFAULT_PLATFORM=linux/amd64`. Its Trivy fallback downloads a Linux
binary: on macOS, put a `trivy` on `PATH` first (a wrapper around
`docker run aquasec/trivy:0.58.1` works).

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
unset. With `STOA_NATIVE_TOOLS_ENABLED=false` the `stoa_*` relay tools that
called it are not registered. The per-tenant tool discovery of the REST MCP
endpoints still dials it on request: see "MCP tools from published
contracts".

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
| `STOA_KEYCLOAK_CLIENT_ID` | `stoa-mcp-gateway` when URL set | OIDC client id. Not the checked `aud` unless `STOA_JWT_AUDIENCE` is empty and audience checks are forced on in code. |
| `STOA_JWT_AUDIENCE` | empty | CSV or JSON. Standalone boot refuses an empty list. `STOA_JWT_AUDIENCES` is not read. A route with no `inboundAuthAudience` is checked against this list. |
| `STOA_KEYCLOAK_CLIENT_SECRET` | unset | Gateway's own client, not the caller. |
| `STOA_KEYCLOAK_ADMIN_PASSWORD` | unset | DCR public-client patch. |
| `STOA_KEYCLOAK_INTERNAL_URL` | unset | Discovery and JWKS fetch base. |
| `STOA_GATEWAY_EXTERNAL_URL` | `http://localhost:8080` | Advertised OAuth base. |
| `STOA_ADMIN_API_TOKEN` | unset | Unset → admin 503. Wrong bearer → 401. |
| `STOA_TRUSTED_PROXIES` | empty | CSV/JSON CIDRs for client IP and scheme. |
| `STOA_PUBLIC_MCP_ENABLED` | `false` | Lets a proxied request reach `/mcp`, the OAuth discovery documents and the health probes. Needs `STOA_KEYCLOAK_URL`. See "Public MCP". |
| `STOA_OAUTH_AUTHORIZATION_SERVERS` | empty (the gateway itself) | `authorization_servers` in the protected resource metadata: issuer URLs, CSV or JSON array. See "Sign-in for MCP clients". |
| `STOA_OAUTH_SCOPES_SUPPORTED` | `openid,profile,email,stoa:read,stoa:write,stoa:admin` | `scopes_supported` in the discovery documents (CSV or JSON array). |

### Control plane and audit

| Variable | Default | Notes |
| --- | --- | --- |
| `STOA_CONTROL_PLANE_URL` | unset | Unset → standalone. No refresh loops. |
| `STOA_CONTROL_PLANE_API_KEY` | unset | Required together with the URL to register. |
| `STOA_AUDIT_SPOOL_DIR` | `/var/lib/stoa-gateway/audit-spool` | Spool is not opened at startup. Standalone mounts nothing here. |
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
| `STOA_MEMORY_LIMIT_MB` | `512` | Backpressure at 80%. Standalone ConfigMap sets `768` under the 1Gi limit. |
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
Keycloak RS256 bearer on `GET /apis/<tenant>/<name>/...`. The gateway stores
that policy in the same `POST /admin/contracts` as the routes, before the
routes are inserted, so the route is not served anonymously between a
contract call and a later policy call. `inboundAuthAudience` (or
`policies[].config.audience`) is the audience checked for that route, even
when the process-wide validator has audience checks off. A route with no
audience of its own is checked against `STOA_JWT_AUDIENCE`. Standalone
refuses to boot when that variable is empty, and refuses the publish when
both the global list and the route audience are empty. Issuer is
`{STOA_KEYCLOAK_URL}/realms/{realm}` (`https://auth.gostoa.dev/realms/stoa`
in the ConfigMap). No header → 401 with `WWW-Authenticate`. Token whose `aud`
contains the policy audience → proxied. Another client's token, `alg: none`,
a broken signature, and an expired token → 401. With no control-plane URL,
a contract without inbound auth is rejected (400) and the route is not
stored. With a control-plane URL, that contract is still published open.

stoactl (stoa-v2 PR #8) is not in this repository. It must send
`inboundAuth: jwt` and `inboundAuthAudience` on the contract. This gateway
does not read `allowUnauthenticatedREST` or `allowWidenedPrefix`. After a
restart the in-memory routes are gone and `GET /apis/...` is 404 until
that same call is published again. `deploy/standalone/republish-contracts.sh`
prints the stoactl POST. There is no disk replay.

The proof sets `STOA_JWT_AUDIENCE=stoa-gateway` and adds a Keycloak
`oidc-audience-mapper` with `included.custom.audience=stoa-gateway` on
client `stoa-caller` only. Client `stoa-no-audience` has no mapper. It also
checks that `POST /admin/contracts` with `X-Forwarded-For` is 404. Nothing
in the script sets `allowUnauthenticatedREST`; that variable does not exist.

```bash
STOA_PROOF_BIN=./stoa-gateway/target/debug/stoa-gateway deploy/standalone/jwt-proof.sh
```

The script prints status codes only. On the cluster, the same calls are:

```text
curl -sS -o /dev/null -w '%{http_code}\n' https://api.gostoa.dev/apis/demo/live-api/ping
curl -sS -o /dev/null -w '%{http_code}\n' https://api.gostoa.dev/apis/demo/live-api/ping \
  -H "authorization: Bearer $ACCESS_TOKEN"
```

The first is 401. The second is 200 when the token's `iss` is
`https://auth.gostoa.dev/realms/stoa` and its `aud` contains `stoa-gateway`.
Callers need the audience mapper on their Keycloak client before the switch.
