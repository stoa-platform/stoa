# AUDIT-RESULTS — claude.ai remote MCP connector fix (CAB-2106)

**Audit date**: 2026-04-17
**Scope**: Phase 1 (code + tests) + Phase 2 step 1 (local curl matrix on running binary).
**Under test**: `stoa-gateway` built from worktree `.claude/worktrees/gateway-mcp-fix`, commit `b8f56b04`, branch `fix/cab-2106-gateway-mcp-sse-accept`.

## Phase 1 — Code + tests — PASS

| Gate | Command | Result |
|------|---------|--------|
| Unit tests | `cargo test --lib mcp::sse` | 39 passed / 0 failed (9 new for `accepts_event_stream`) |
| Full test suite | `cargo test` | 2158 lib + 47 contract + 52 integration + 15 resilience + 26 security, all green |
| Clippy strict | `RUSTFLAGS=-Dwarnings cargo clippy --all-targets -- -D warnings` | clean |
| Rustfmt | `cargo fmt --check` | clean |
| PR size | `git diff --cached --stat` | 464 insertions / 2 deletions across 4 files (production ≈70 LOC) |

## Phase 2 step 1 — Local binary curl matrix — PASS

### Setup
- Gateway launched from the worktree with `STOA_PORT=8765 STOA_JWT_VALIDATION_DISABLED=true STOA_OTEL_ENDPOINT="" cargo run`.
- `/health` returned `200` before the matrix started.

### Accept matrix

| # | Accept header | Expected Content-Type | Observed Content-Type | Body shape | Mcp-Session-Id |
|---|---------------|------------------------|------------------------|------------|----------------|
| A | `text/event-stream` (claude.ai pattern) | `text/event-stream` | `text/event-stream` | `event: message\ndata: {"jsonrpc":"2.0",...}` | present |
| B | `application/json, text/event-stream` (MCP-compliant client) | `text/event-stream` | `text/event-stream` | SSE frame as above | present |
| C | `application/json` (legacy) | `application/json` | `application/json` | JSON body, `content-length: 412` | present |
| D | *absent* (curl default) | `application/json` | `application/json` | JSON body | present |
| E | `*/*` | `application/json` (back-compat) | `application/json` | JSON body | present |

### Full claude.ai-style flow

1. `POST /mcp/sse` with `Accept: text/event-stream`, body = `initialize` → `200`, `content-type: text/event-stream`, `mcp-session-id: cc3fd415-aa6c-42b1-be24-dbfc185be52e`, SSE `event: message` with the initialize response.
2. `POST /mcp/sse?sessionId=cc3fd415-...` with `Accept: text/event-stream`, body = `tools/list` → `200`, `content-type: text/event-stream`, same `mcp-session-id` echoed, SSE frame with the full tools array (15 tools: `stoa_api_spec`, `stoa_cache_invalidate`, `stoa_tenants`, `stoa_alerts`, `stoa_uac`, `stoa_platform_health`, `stoa_subscription`, `stoa_catalog`, `stoa_cache_load`, `stoa_tools`, `stoa_cache_get`, `stoa_logs`, `stoa_security`, `stoa_platform_info`, `stoa_metrics`).
3. `transfer-encoding: chunked` confirmed on the SSE responses.

Pre-fix observation (reproduced earlier against prod `mcp.gostoa.dev`): identical curl against the unpatched binary returned `content-type: application/json` regardless of Accept, which is what the claude.ai connector rejected.

### Evidence artefacts
Raw curl output captured under `/tmp/sse_*.{hdr,body}` during the run (not copied into git to keep the audit note short). Reproduce with:
```bash
cargo run  # in worktree stoa-gateway/
for H in 'text/event-stream' 'application/json, text/event-stream' 'application/json'; do
  curl -sS -D - --max-time 3 -X POST http://127.0.0.1:8765/mcp/sse \
    -H "Accept: $H" -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
done
```

## Phase 4 — InitializeResult shape hotfix (CAB-2112) — PASS

### Actual root cause for the claude.ai UI error

User-captured Anthropic Toolbox / Pydantic error (the generic `ofid_*` refs came from this):

```
Network error connecting to MCP server.
ValidationError: 1 validation error for InitializeResult
capabilities.experimental.transports
  Input should be a valid dictionary [type=dict_type]
```

`handle_initialize` was emitting `"experimental": { "transports": ["sse", "websocket"] }`. MCP 2025-11-25 / the Anthropic Pydantic schema require every value under `capabilities.experimental` to be a feature-config **dict**. Shipping an array rejected the whole `InitializeResult`, which claude.ai surfaced as the opaque "Authorization with the MCP server failed".

### Fix + deploy

- **PR #2414** (CAB-2112) — drops the non-standard `experimental.transports` field entirely; 2 regression tests lock the contract (`regression_cab_2110_experimental_entries_are_all_dicts`, `regression_cab_2110_initialize_result_shape_matches_spec`).
- **PR #2416** — release-please `stoa-gateway 0.9.8`, merged.
- ArgoCD rolled `ghcr.io/stoa-platform/stoa-gateway:dev-3570f39193c85ae803c2fc72f3234093e061a1eb` on OVH MKS.

### Post-deploy validation

`curl POST https://mcp.gostoa.dev/mcp/sse initialize` response capabilities keys: `elicitation, logging, prompts, resources, tokenOptimization, tools`. `experimental` absent.

Same curl flow returned the broken array shape before 0.9.8. Pydantic no longer has a surface to reject.

## Lessons learned

- **Extrapolating a "full chain validation" from MCP Inspector + Claude Code CLI was the wrong call**. Inspector used streamable-http happy-path with a generous JSON-schema validator; Anthropic's Toolbox uses Pydantic which is stricter. The claude.ai GUI error message only surfaced the actual validation failure when the user captured and shared the browser-level error.
- **Always drive the real client of record** (claude.ai in Chrome, not MCP Inspector CLI) when closing a "works on prod" audit.
- **Three root causes in series**:
  1. Accept header never honoured → CAB-2106
  2. Discovery methods 401 during capability negotiation → CAB-2109
  3. `experimental.transports` shape breaks Pydantic `InitializeResult` → CAB-2112
- Adjacent but unrelated prod bugs surfaced in logs during the hunt: broken `chat-completions-gpt4o` tool (DNS-less `stoa-aoai.openai.azure.com`) trips the per-tool circuit breaker; ~5 UUID-named stale tools clutter `tools/list`; OTLP `BatchSpanProcessor` saturation. Not blocking claude.ai once CAB-2112 landed.

## Phase 3 — public_methods hotfix (CAB-2109) — PASS

### Second root cause found after CAB-2106 deploy

`claude.ai` connector kept failing with Anthropic ref `ofid_5f1fcc086cd04144` even though the Accept-header fix was live. Root cause confirmed via MCP Inspector (`--transport streamable-http`):

```
POST /mcp/sse initialize                → 200 ✓
POST /mcp/sse notifications/initialized → 204 ✓
POST /mcp/sse tools/list                → 200 ✓
POST /mcp/sse logging/setLevel          → 401 ✗
POST /mcp/sse resources/list            → 401 ✗
POST /mcp/sse prompts/list              → 401 ✗
```

`public_methods` only whitelisted `initialize`, `ping`, `tools/list`, `notifications/initialized`, `notifications/cancelled`. The remaining discovery methods advertised in the `initialize` capabilities response (logging, resources, prompts, etc.) were gated behind auth, breaking capability negotiation before the OAuth flow attaches a Bearer token.

### Fix + deploy

- **PR #2411** (CAB-2109) merged `fb082f8c` — factored `PUBLIC_METHODS` into a shared const (both `handle_sse_post` and `process_single_request`), extended whitelist with 8 read-only discovery methods, added 3 regression tests.
- **PR #2412** (release-please `stoa-gateway 0.9.7`) merged `400ae970`.
- ArgoCD rolled `ghcr.io/stoa-platform/stoa-gateway:dev-fb082f8cfac6c5eb5bcf6b48249653653c7beebe` on OVH MKS, 2/2 pods Running.

### Prod matrix validation on 0.9.7

All 11 discovery methods anonymous (no Bearer):

| Method | Status |
|--------|--------|
| `ping` | 200 |
| `tools/list` | 200 |
| `resources/list` | 200 |
| `resources/templates/list` | 200 |
| `resources/read` | 200 |
| `prompts/list` | 200 |
| `prompts/get` | 200 |
| `completion/complete` | 200 |
| `roots/list` | 200 |
| `logging/setLevel` | 200 |
| `notifications/initialized` | 204 |
| `tools/call` (still must 401) | 401 + `WWW-Authenticate: Bearer` |

Tool surface remains protected. MCP Inspector `--cli --transport streamable-http` now lists the full 15-tool catalog without `Authentication required` error.

## Phase 2 — prod deploy + curl validation — PASS

### Deploy chain
- PR #2404 merged `a738ff25` — unblocked Gateway CI on main (pre-existing `/tmp` tee failure on self-hosted runner).
- PR #2402 (CAB-2106) merged `bd286867` — rebased onto fresh main.
- Release-please opened PR #2405 (`chore(main): release stoa-gateway 0.9.6`) automatically, then merged `bb5046f6`.
- ArgoCD / image-updater on OVH MKS picked up the new image within minutes. Running pods on the `stoa-system` namespace at validation time:
  - `stoa-gateway-7684665f49-rmpqx` / `stoa-gateway-7684665f49-tz7vd`
  - image: `ghcr.io/stoa-platform/stoa-gateway:dev-bd2868675d744e9aa34969630a110690e5fbbe40`
  - status: `1/1 Running`, age 18 min.

### Production curl matrix (`mcp.gostoa.dev`)

| # | Accept header | Observed Content-Type | Body |
|---|---------------|------------------------|------|
| A | `text/event-stream` (claude.ai) | `text/event-stream` | `event: message\ndata: {"jsonrpc":"2.0","result":{"capabilities":{...` |
| B | `application/json, text/event-stream` | `text/event-stream` | SSE frame |
| C | `application/json` | `application/json` | `{"jsonrpc":"2.0","result":...}` (content-length 412) |

Mcp-Session-Id header present on all 3. HTTP/2 200 everywhere. No redirect loop, no 401.

### Remaining (manual / GUI-bound, out of Claude Code scope)

- [ ] Attach a claude.ai test connector at `https://mcp.gostoa.dev/mcp/sse`; confirm "Connected" + tools list + single tool call succeeds. Expected: Anthropic error ref `ofid_d2fef633fa45878c` no longer reproduces.
- [ ] Capture screenshot of claude.ai UI + `kubectl -n stoa-system logs -l app=stoa-gateway` showing one-shot `initialize → tools/list → tools/call` sequence (no DCR retry loop).

## Phase 3+ — scope of separate tickets

- **Soft-auth close on `/mcp/*`** — P1 follow-up (`gotcha_gateway_soft_auth_mcp.md`).
- **CORS annotations on ingress** — P2 (dual-repo chart sync).
- **OTLP `BatchSpanProcessor` saturation** — P3 log noise.
