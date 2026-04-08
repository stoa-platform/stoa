# Spec: CAB-2006 — stoactl mcp subcommand + shell completions

## Problem

`stoactl` has no dedicated command to interact with MCP servers and tools. The client already has `CreateMCPServer`/`AddToolToServer`, but users cannot **list servers, list tools, call a tool, or check MCP health** from the CLI. Shell completions (bash/zsh/fish) are also missing despite Cobra supporting them natively.

## Goal

A developer evaluating STOA can run `stoactl mcp list-tools` within 30 seconds of install and see available MCP tools. All 4 MCP subcommands work against both CP API (default) and gateway directly (`--gateway`). Shell completions install with a single command.

## API Contract

### CP API endpoints (source of truth — already exist)

```
GET  /v1/admin/mcp/servers                          → MCPServerListResponse { servers[], total_count }
GET  /v1/admin/mcp/servers/{server_id}               → MCPServerResponse { id, name, ..., tools[] }
POST /v1/admin/mcp/servers/{server_id}/tools/invoke   → ToolInvokeResponse { result, error }
GET  /v1/admin/mcp/servers/health                    → { status, version, uptime }
```

### Gateway direct endpoints (--gateway flag)

```
GET  /mcp/v1/tools          → { tools[] }
POST /mcp/v1/tools/invoke   → { result }
GET  /health                → { status, version }
```

### Client methods to add

```go
// pkg/client/client.go
func (c *Client) ListMCPServers() (*types.MCPServerListResponse, error)
func (c *Client) ListTools(serverID string) (*types.MCPToolListResponse, error)
func (c *Client) CallTool(serverID, toolName string, input json.RawMessage) (*types.MCPToolCallResponse, error)
func (c *Client) MCPHealth() (*types.MCPHealthResponse, error)
```

### Types to add

```go
// pkg/types/mcp.go
type MCPServerSummary struct {
    ID          string `json:"id"`
    Name        string `json:"name"`
    DisplayName string `json:"display_name"`
    Category    string `json:"category"`
    Status      string `json:"status"`
    ToolCount   int    `json:"tool_count"`
}

type MCPServerListResponse struct {
    Servers    []MCPServerSummary `json:"servers"`
    TotalCount int               `json:"total_count"`
}

type MCPToolSummary struct {
    Name        string `json:"name"`
    DisplayName string `json:"display_name"`
    Description string `json:"description"`
    Enabled     bool   `json:"enabled"`
    ServerName  string `json:"server_name"`
}

type MCPToolListResponse struct {
    Tools []MCPToolSummary `json:"tools"`
}

type MCPToolCallResponse struct {
    Result json.RawMessage `json:"result"`
    Error  string          `json:"error,omitempty"`
}

type MCPHealthResponse struct {
    Status  string `json:"status"`
    Version string `json:"version,omitempty"`
    Uptime  string `json:"uptime,omitempty"`
}
```

## Acceptance Criteria

- [ ] AC1: `stoactl mcp list-servers` returns a table with columns: NAME, DISPLAY NAME, CATEGORY, STATUS, TOOLS when servers exist
- [ ] AC2: `stoactl mcp list-servers` prints "No MCP servers found" when no servers exist
- [ ] AC3: `stoactl mcp list-servers -o json` returns JSON array of servers
- [ ] AC4: `stoactl mcp list-servers -o yaml` returns YAML list of servers
- [ ] AC5: `stoactl mcp list-tools` returns a table with columns: NAME, DISPLAY NAME, SERVER, ENABLED when tools exist
- [ ] AC6: `stoactl mcp list-tools --server <name>` filters tools by server
- [ ] AC7: `stoactl mcp list-tools` prints "No tools found" when no tools exist
- [ ] AC8: `stoactl mcp call <tool-name> --server <server> --input '{"key":"val"}'` invokes the tool and prints the JSON result
- [ ] AC9: `stoactl mcp call` without tool name prints usage error with exit code 2
- [ ] AC10: `stoactl mcp call <tool> --input 'invalid-json'` returns a validation error before making the API call
- [ ] AC11: `stoactl mcp health` returns status, version, uptime in table format
- [ ] AC12: `stoactl mcp health` returns exit code 1 when MCP endpoint is unreachable
- [ ] AC13: `--gateway <url>` flag on `list-tools`, `call`, `health` bypasses CP API and hits gateway directly
- [ ] AC14: `stoactl completion bash` outputs valid bash completion script to stdout
- [ ] AC15: `stoactl completion zsh` outputs valid zsh completion script to stdout
- [ ] AC16: `stoactl completion fish` outputs valid fish completion script to stdout
- [ ] AC17: `stoactl completion` without shell argument prints usage listing the 3 supported shells
- [ ] AC18: All 4 new client methods have unit tests with httptest mocks
- [ ] AC19: `go vet ./...` and `go build ./...` pass with zero errors

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| No auth token | Missing `STOA_API_KEY` + no keyring | Error: "not authenticated", exit code 3 | Must |
| API returns 401 | Expired/invalid token | Error with "authentication failed", exit code 3 | Must |
| API returns 500 | Server error | Error: "API error (500): \<body\>", exit code 1 | Must |
| Server not found | `--server nonexistent` | Error: "server 'nonexistent' not found", exit code 4 | Must |
| Tool not found | `stoactl mcp call ghost --server s1` | Error: "tool 'ghost' not found", exit code 4 | Must |
| Empty input | `stoactl mcp call tool --server s1` (no `--input`) | Send `{}` as default input | Should |
| Large JSON result | Tool returns 1MB+ response | Stream to stdout without OOM | Should |
| Gateway unreachable | `--gateway http://dead:1234` | Error + exit code 1, timeout after 10s | Must |
| Mixed flags | `-o json --gateway url` | Both flags compose correctly | Must |

## Out of Scope

- Interactive TUI mode for tool invocation
- `stoactl diff` command
- Extended `delete` for MCP resources
- Plugin system
- Tool input schema validation against `inputSchema` (future: `--validate` flag)
- MCP Streamable HTTP transport (gateway uses REST, not JSON-RPC)

## Security Considerations

- [x] Auth required: Bearer token (`STOA_API_KEY` or keyring). All MCP admin endpoints require `cpi-admin` or `tenant-admin` role
- [x] No client-side logging of `--input` payloads (tool call input/output may contain PII)
- [x] Rate limiting: Server-side (100/min list, 30/min calls) — no client-side throttling needed
- [x] `--gateway` flag bypasses CP API RBAC — document this clearly in `--help` text

## Dependencies

- CP API MCP admin endpoints exist (`/v1/admin/mcp/servers` — `mcp_admin.py:395+`)
- Gateway health endpoint exists (`/health`)
- Gateway tools endpoint exists (`/mcp/v1/tools`)
- Cobra v1.8.0 in go.mod (completion support built-in)
- `pkg/output` package handles table/json/yaml formatting

## Council Validation — 8.50/10 Go

| Persona | Score | Verdict |
|---------|-------|---------|
| Chucky (Devil's Advocate) | 8/10 | Go |
| OSS Killer (VC Skeptic) | 9/10 | Go |
| Archi 50x50 (Architect) | 8/10 | Go |
| Better Call Saul (Legal) | 9/10 | Go |

### Adjustments applied

1. **Name→ID resolution**: `--server <name>` resolves name→ID client-side (list servers → find match → get tools by server ID)
2. **Default pagination**: CLI defaults to `page=1, page_size=100` for list commands. No `--limit` flag in v1

## Notes

- Follow existing patterns: `NewXxxCmd()` factory → `rootCmd.AddCommand()` in `root.go`
- Client `do()` method handles auth headers, tenant, JSON marshaling — reuse for all 4 methods
- Output: use `output.Printer` with `--output/-o` flag (table default, json, yaml)
- Exit codes: follow convention in `root.go:85-93` (0=OK, 1=Error, 2=Misuse, 3=AuthFailed, 4=NotFound)
- `--gateway` flag: create a secondary `http.Client` targeting the gateway URL instead of CP API
- `--server <name>` on `list-tools` and `call`: client lists all servers, matches by name, uses the server ID for the API call
- Tool invoke endpoint on CP API may need to be created if it doesn't exist yet — verify during Phase 2
