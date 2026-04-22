# TEST-PLAN — GO-2 pre-merge validation

Status: automated checks green (104 tests `-race`, `go vet`, `golangci-lint`,
2 mock-CP smoke tests). This file documents the MANUAL end-to-end checks
that the user runs against a real CP-API before merging `refactor/go-2-connect-split`.

All runnable from `stoa-go/` after `make build-connect`.

---

## What's already automated

Run these any time — all green as of commit `e78e89d45`:

```bash
cd stoa-go/
go vet ./...
go test ./internal/connect/... -race -count=1        # 104 tests
$HOME/go/bin/golangci-lint run ./...
go build ./cmd/...
```

Mock-CP integration smokes reproduced below for reference. These mock the
CP-API with a 60-line Python server and exercise the hot paths end-to-end
against the real `stoa-connect` binary (not Go httptest).

### Smoke 1 — Register + Heartbeat + clean shutdown (GO-2 S1 + S4 + S9)

```bash
cat > /tmp/mock_cp.py << 'EOF'
import http.server, json, threading, time
events = {"register": 0, "heartbeat": 0}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **kw): pass
    def do_POST(self):
        _ = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        if self.path.endswith("/register"):
            events["register"] += 1
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"id":"gw-mock-42","name":"mock","environment":"dev","status":"active"}).encode())
        elif self.path.endswith("/heartbeat"):
            events["heartbeat"] += 1
            self.send_response(204); self.end_headers()
        else: self.send_response(404); self.end_headers()
srv = http.server.HTTPServer(("127.0.0.1", 9999), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(8); srv.shutdown()
print(json.dumps(events))
EOF
python3 /tmp/mock_cp.py &
sleep 0.5
STOA_CONTROL_PLANE_URL=http://127.0.0.1:9999 \
STOA_GATEWAY_API_KEY=test-key \
STOA_INSTANCE_NAME=smoke-agent \
STOA_HEARTBEAT_INTERVAL=500ms \
STOA_CONNECT_PORT=8091 \
timeout 6 ./bin/stoa-connect
wait
```

Expected: 1 register, ~10 heartbeats, `"heartbeat stopped"` on SIGTERM.

### Smoke 2 — 404 → re-register threshold (ADR-057, reRegisterThreshold=3)

Same harness, but the mock returns 404 on every heartbeat. Expected:
`heartbeat 404 (1/3)`, `(2/3)`, `(3/3)` → `"gateway purged from CP,
re-registering..."` → `"re-registered with CP: id=gw-rev-2"` → loop.

Validated 2026-04-22: 6 re-registrations in 5s with interval=300ms, each
preceded by exactly 3× 404. State flips correctly (new gateway_id is
read back after ClearGatewayID + Register).

---

## Manual end-to-end checks before merge

These require a real CP-API reachable. Recommended path: a local Tilt
stack (`cd ~/hlfh-repos/stoa && tilt up`) with the CP-API pod up and
reachable at `https://api.gostoa.local` (or whatever Tilt binds).

The agent config should target that CP and a real third-party gateway
admin (kong/gravitee/webmethods) or the webmethods pod in the Tilt stack
if you have one running.

### Check E1 — Happy path (register + heartbeat for 60s)

```bash
export STOA_CONTROL_PLANE_URL=https://api.gostoa.local
export STOA_GATEWAY_API_KEY=<from vault or Tilt secret>
export STOA_INSTANCE_NAME=go2-test-$(date +%s)
export STOA_ENVIRONMENT=development
export STOA_GATEWAY_ADMIN_URL=http://localhost:8001  # kong admin e.g.
./bin/stoa-connect
```

Watch for:
- [ ] `registered with CP: id=<uuid>` within 1s
- [ ] `discovery started: type=<kong|gravitee|webmethods>`
- [ ] `starting policy sync loop (interval=60s)`
- [ ] `starting route sync loop (interval=30s)` (if SSE disabled)
- [ ] Heartbeat every 30s
- [ ] `GET /health` on :8090 returns `{"status":"ok", ...}` with correct gateway_id
- [ ] `GET /metrics` on :8090 exposes `stoa_connect_*` counters

Ctrl+C → expect:
- [ ] `shutting down...`
- [ ] `heartbeat stopped`, `discovery stopped`, `sync stopped`, `route-sync stopped`
- [ ] Process exits within 5s (no stuck goroutines)

### Check E2 — SSE deployment stream (ADR-059) — CRITICAL for B.1 fix

Requires the CP-API SSE endpoint active and a deployment event to trigger.

```bash
export STOA_SSE_ENABLED=true
./bin/stoa-connect
# In another terminal, trigger a deployment via CP admin UI or CLI
stoactl uac deploy <api> <gateway>
```

Watch for:
- [ ] `starting SSE deployment stream (initial=2s max=60s)`
- [ ] `sse-stream: connected to https://api.gostoa.local/v1/internal/gateways/<id>/events`
- [ ] On deployment: `sse-stream: received deployment <dep-id> (status=pending)`
- [ ] `sse-stream: sync deployment <dep-id> applied`
- [ ] **In CP-API database or admin UI**: the ack carries `generation` != 0
      (B.1 regression — see REWRITE-BUGS.md)

### Check E3 — SSE reconnect on network drop (B.6 fix + retry policy)

With SSE stream active from E2:

```bash
# Terminal 2: suspend CP-API pod (drops the SSE connection mid-stream)
kubectl scale deployment control-plane-api -n stoa --replicas=0
sleep 10
kubectl scale deployment control-plane-api -n stoa --replicas=1
```

Watch for:
- [ ] `sse-stream: terminal error: <concrete cause> (reconnecting in 2s, attempt 1)`
- [ ] Backoff progression: `attempt 1 → 2s`, `attempt 2 → 4s`, `attempt 3 → 8s`…
- [ ] After CP restart: reconnect succeeds, attempt counter resets
- [ ] No duplicate sync of routes already applied (idempotency)

### Check E4 — Oversized SSE event (F.6 regression guard)

Trigger a deployment whose `desired_state` exceeds 64 KB (a realistic
webMethods OpenAPI spec with ~50 paths). Pre-S5, this would silently
truncate; now the scanner buffer is 1 MB.

- [ ] Large event flows through to `adapter.SyncRoutes` without
      `bufio.ErrTooLong` in the logs.
- [ ] If you want to force the failure path: craft a >2 MB event on the
      CP side — expect `sse-stream: terminal error: SSE read: bufio.Scanner: token too long`.

### Check E5 — Vault credential sync

Requires Vault reachable with a pre-populated `stoa/data/consumers/<tenant_id>`.

```bash
export VAULT_ADDR=https://hcvault.gostoa.dev
export VAULT_ROLE_ID=<role>
export VAULT_SECRET_ID=<secret>
export STOA_TENANT_ID=<tenant>
./bin/stoa-connect
```

Watch for:
- [ ] `vault: authenticated via AppRole (lease=<seconds>s)`
- [ ] `starting credential sync loop (interval=60s, tenant=<tenant>)`
- [ ] `credential-sync: injected N credentials` on first cycle
- [ ] Gateway (kong/gravitee) actually has the consumer credentials after cycle
- [ ] TTL approach: if you set Vault token TTL < 5min, expect
      `vault: token renewal warning` or `vault: re-authenticating via AppRole`

### Check E6 — goroutine leak audit (SIGTERM response time)

From any running E1..E5 scenario:

```bash
# Send SIGTERM and time the shutdown
time kill -TERM $(pgrep -f stoa-connect)
```

- [ ] Process exits in < 5s consistently (Ctrl+C shuts down all 6 loops cleanly)
- [ ] No `goroutine NN [running]` stuck traces visible in the last output
- [ ] If you want to verify programmatically:
      `GOTRACEBACK=all kill -ABRT $(pgrep -f stoa-connect)` then grep the
      core dump for `chan receive` or `IO wait` goroutines that outlive ctx.

---

## Out-of-scope items documented elsewhere

The following are KNOWN latent issues documented but NOT fixed in GO-2:

- F.3 / F.4 / F.5 / F.7 / F.8 / F.9 — see `REWRITE-BUGS.md`
- C.1 — `OIDCAdapter` asymmetric delete surface (would need GO-1-bis)
- C.2 — `AliasAdapter` dead code on agent side

None block merging GO-2; all are listed as follow-up tickets.

---

## Sign-off checklist before merge

- [ ] `go vet ./...` clean
- [ ] `go test ./internal/connect/... -race -count=1` → 104 tests green
- [ ] `$HOME/go/bin/golangci-lint run ./...` clean
- [ ] Smoke 1 (register + heartbeat) passes locally
- [ ] Smoke 2 (404 → re-register) passes locally
- [ ] E1 (happy path) validated against real Tilt stack
- [ ] E2 (SSE deployment + generation in ack) validated
- [ ] E3 (SSE reconnect) validated OR acknowledged as covered by unit tests
- [ ] E6 (SIGTERM < 5s) validated
- [ ] E4 (oversized event) — optional, covered by unit test
      `TestSSEStreamAcceptsLargeEvent` already
- [ ] E5 (Vault) — optional, credentials.go path not touched by GO-2
