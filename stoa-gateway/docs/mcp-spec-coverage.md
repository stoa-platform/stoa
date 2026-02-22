# MCP Spec Coverage — STOA Gateway

> Generated: 2026-02-22 | Spec version: 2025-03-26 | CAB-1333

## Method Coverage Matrix

### Core Lifecycle

| Method | Direction | Status | Notes |
|---|---|---|---|
| `initialize` | C→S | ✅ | Protocol version negotiation, capability exchange |
| `notifications/initialized` | C→S | ✅ | Client confirmation (204 response) |
| `ping` | C→S | ✅ | Returns `{}` |

### Tools

| Method | Direction | Status | Notes |
|---|---|---|---|
| `tools/list` | C→S | ✅ | Pagination cursor supported |
| `tools/call` | C→S | ✅ | Full UAC + OPA enforcement |
| `notifications/tools/list_changed` | S→C | ❌ | Not pushed when registry refreshes |

### Resources

| Method | Direction | Status | Notes |
|---|---|---|---|
| `resources/list` | C→S | ✅ | Stub — maps tools to resources |
| `resources/read` | C→S | ❌ | **Gap** — URI-based resource read missing |
| `resources/templates/list` | C→S | ❌ | Not implemented, not advertised |
| `resources/subscribe` | C→S | ❌ | Advertised as `subscribe: false` — intentional |
| `resources/unsubscribe` | C→S | ❌ | N/A (subscribe disabled) |
| `notifications/resources/list_changed` | S→C | ❌ | Not pushed |
| `notifications/resources/updated` | S→C | ❌ | Not pushed |

### Prompts

| Method | Direction | Status | Notes |
|---|---|---|---|
| `prompts/list` | C→S | ❌ | **Gap** — advertised in `capabilities`, not routed |
| `prompts/get` | C→S | ❌ | **Gap** — advertised, not routed |
| `notifications/prompts/list_changed` | S→C | ❌ | Not pushed |

### Logging

| Method | Direction | Status | Notes |
|---|---|---|---|
| `logging/setLevel` | C→S | ❌ | **Gap** — `"logging": {}` advertised in capabilities |
| `notifications/message` | S→C | ❌ | **Gap** — log push to client missing |

### Completion (Optional)

| Method | Direction | Status | Notes |
|---|---|---|---|
| `completion/complete` | C→S | ❌ | Not advertised, not implemented |

### Sampling / Roots (Complex — Deferred)

| Method | Direction | Status | Notes |
|---|---|---|---|
| `sampling/createMessage` | S→C | 🔜 | Server requests LLM call from client; requires bidirectional request/response over SSE. Phase 2+ scope. |
| `roots/list` | S→C | 🔜 | Server requests client's filesystem roots. Same bidirectional complexity. Phase 2+ scope. |

## Capability Advertisement vs. Implementation

| Capability | Advertised | Implemented |
|---|---|---|
| `tools.listChanged` | `true` | ❌ notifications not sent |
| `resources.subscribe` | `false` | ✅ intentionally disabled |
| `resources.listChanged` | `false` | ✅ intentionally disabled |
| `prompts.listChanged` | `false` | ❌ methods not routed |
| `logging` | `{}` | ❌ `logging/setLevel` not handled |
| `elicitation` | `{}` | ⚠️ Types defined, wiring pending |
| `tokenOptimization` | `{...}` | ✅ fully implemented |

## Priority Ranking

Based on client demand (Claude Desktop, Cursor, VS Code Copilot):

| Priority | Method | Reason |
|---|---|---|
| P0 | `prompts/list` + `prompts/get` | Already advertised — client will request immediately |
| P0 | `logging/setLevel` | Already advertised — client expects to call this |
| P1 | `resources/read` | Natural extension of `resources/list` |
| P1 | `notifications/message` | Required for logging to actually work |
| P2 | `notifications/tools/list_changed` | Enables live tool registry updates |
| P3 | `completion/complete` | Useful for IDE argument autocomplete |
| Deferred | `sampling/createMessage` | Requires bidirectional SSE request/response |
| Deferred | `roots/list` | Same complexity as sampling |

## Phase 2 Implementation Scope

Methods to implement (CAB-1333 Phase 2):
1. `prompts/list` — returns `{ prompts: [] }` (extensible, no built-in prompts yet)
2. `prompts/get` — returns `PromptNotFound` (-32002) for unknown names
3. `logging/setLevel` — persists level in session metadata
4. `resources/read` — resolves `stoa://tools/{name}` URIs
5. `notifications/message` — push log events via NotificationBus when level is set

## Phase 3 Implementation Scope

Conformance tests (CAB-1333 Phase 3):
- Contract tests: every method returns correct JSON shape
- Capability parity: every advertised capability has a working handler
- Error contract: `METHOD_NOT_FOUND` for unregistered methods
- Batch: all new methods work in batch requests
