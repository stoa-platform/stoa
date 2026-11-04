# Isolated public demo (manual opt-in)

This overlay is not referenced by any root application. The current bootstrap
uses ingress-nginx (`deploy/bootstrap/argocd/app-ingress-nginx.yaml`); its gateway
applications select only dev and staging. No cluster operations run in CI here.
Do not add this directory to an ApplicationSet or recursive sync.

Ingress authenticates a single dedicated demo key as the Basic password for user
`demo`, using `demo-access/auth` (bcrypt htpasswd). The gateway's control-plane
API-key mechanism is not used. The only public backend is the NGINX edge sidecar:
its independent IP and single-key shared buckets return HTTP 429. The shared
bucket deliberately covers all IPs and all encodings of that one credential.
NGINX uses the controller-overwritten X-Real-IP, then drops all incoming headers
except Content-Type and User-Agent before proxying. Never trust client-supplied
forwarding headers in the ingress controller; DevOps must verify its trusted
proxy configuration preserves the real public client IP before publication.

The Job upserts two stable route IDs through the namespace-only admin Service.
The bootstrap sidecar repeats the same idempotent upserts, including after a
process/container restart; readiness checks the actual registry. This avoids a
cluster API token or a controller that recreates Jobs. Replay the Job explicitly
by deleting it and reapplying the overlay. Admin has no public Service port or
Ingress rule. Echo only returns explicit fields; weather is static and fictional.
No user-supplied URL is fetched. Images are pinned; there is one gateway replica
so the shared key bucket cannot be multiplied by scaling. Public health shares
the request budgets; readiness uses the local socket and admin registry so a
client burst cannot withdraw the endpoint.

## DevOps deployment only

1. Verify enforcing NetworkPolicy support, ingress controller pod labels and DNS
   pod labels against the policy selectors. Verify trusted client IP handling.
   Prepare an isolated checkout; set `DEMO_HOST`, `DEMO_CERT_FILE`, and
   `DEMO_TLS_KEY_FILE` privately. Use a new certificate/private key for this demo.
2. Create the namespace, then generate fresh secrets specifically for this demo.
   Never reuse repository examples, platform credentials, or existing TLS keys.
   The following commands are instructions, not an automated deployment:

   ```sh
   umask 077
   DEMO_SECRET_DIR=$(mktemp -d)
   export DEMO_SECRET_DIR
   python3 - <<'PY'
   import os, pathlib, secrets
   root = pathlib.Path(os.environ['DEMO_SECRET_DIR'])
   for name in ('token', 'password'):
       (root / name).write_text(secrets.token_hex(32))
   PY
   htpasswd -iBc "$DEMO_SECRET_DIR/auth" demo < "$DEMO_SECRET_DIR/password"
   kubectl apply -f k8s/gateways/overlays/demo/namespace.yaml
   kubectl -n demo create secret generic demo-admin --from-file=token="$DEMO_SECRET_DIR/token"
   kubectl -n demo create secret generic demo-access --from-file=auth="$DEMO_SECRET_DIR/auth"
   kubectl -n demo create secret tls demo-tls --cert="$DEMO_CERT_FILE" --key="$DEMO_TLS_KEY_FILE"
   ```

3. Substitute `demo.invalid` in both Ingress host fields with the approved
   `DEMO_HOST` in that checkout. Build and schema-validate; review the render.
   Run `kustomize build k8s/gateways/overlays/demo | kubectl apply -f -`.
   Wait for both Deployments and the Job; verify readiness after restarting only
   the gateway container. Keep the demo password in a private client config;
   do not put it in command arguments, logs, shell tracing, or evidence files.
4. Before DevOps publishes DNS/tunnel, run the four proofs below. Remove temporary
   secret files securely under the operator's normal secret-handling procedure.
5. Roll back using `kubectl delete namespace demo`. DevOps separately removes any
   DNS/tunnel publication. No shared namespace or platform Secret is modified.

## Required deployment proofs

- Send Authorization, Cookie, X-Forwarded-*, CF-* and an internal header with
  distinguishable markers using a private client config; only method, path,
  query, Content-Type, User-Agent and bounded body appear. Test 64 KiB succeeds
  and 64 KiB + 1 returns 413. Missing/incorrect demo authentication returns 401.
- Burst authenticated calls from one IP for 429, then from several real IPs to
  prove the shared key budget. Spoof forwarding headers: the IP bucket must not
  change. Do not record credentials or real IPs in proof output.
- With valid authentication, `/admin`, `/metrics`, `/mcp`, `/mcp/tools/list`,
  `/sse` and unknown demo routes return 404; health and the two demo routes work.
- From an ephemeral diagnostic container in each demo workload's network
  namespace, attempt TCP connections to a DevOps-selected control-plane Service
  using private destination variables: all time out. Also prove DNS and the
  allowed gateway-to-echo flow work. Do not grant diagnostic pods extra labels
  or policies. A local YAML validation cannot prove live CNI enforcement.

Local checks: `kustomize build`, `kubeconform -strict -summary`, and
`python3 -m unittest discover -s k8s/gateways/overlays/demo -p 'test_*.py'`.
The rate-limit behavior uses standard [NGINX limit_req](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html).
