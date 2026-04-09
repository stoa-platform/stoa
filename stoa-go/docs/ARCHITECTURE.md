# stoactl Architecture

## Auth Model

stoactl supports two authentication contexts:

| Context | Flag | Token Source | Use Case |
|---------|------|-------------|----------|
| **Tenant** (default) | — | User OIDC token (device flow) | Day-to-day operations scoped to a tenant |
| **Admin** | `--admin` | Service account token | Cross-tenant admin operations |

Token resolution order (both contexts):
1. Environment variable (`STOA_API_KEY` / `STOA_ADMIN_KEY`)
2. OS Keychain via go-keyring
3. `~/.stoa/tokens` file (deprecated, user context only)

## Package Structure

```
stoa-go/
  cmd/stoactl/main.go              # Entry point
  internal/cli/cmd/                 # Cobra commands
    root.go                         # Root cmd + --admin flag
    get/  apply/  delete/           # Resource commands
    auth/ config/ mcp/ ...          # Feature commands
  pkg/
    client/                         # HTTP client library
      client.go                     # Base client (auth, HTTP plumbing)
      catalog/catalog.go            # API catalog operations
      audit/audit.go                # Audit log queries (stub)
      trace/trace.go                # Trace queries (stub)
      quota/quota.go                # Quota management (stub)
      testutil/testutil.go          # MockTransport + TestClient
    config/config.go                # Multi-context config (~/.stoa/config)
    keyring/keyring.go              # OS keychain abstraction
    output/output.go                # Table/YAML/JSON formatting
    types/                          # Shared type definitions
```

## Sub-Package Convention

Each sub-package under `pkg/client/` follows this pattern:

```go
package catalog

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
    Do(method, path string, body any) (*http.Response, error)
}

type Service struct {
    doer Doer
}

func New(doer Doer) *Service {
    return &Service{doer: doer}
}
```

The `Doer` interface is defined locally in each sub-package (Go structural typing).
This avoids import cycles between `client` and its children.

## How to Add a New Command

1. **Create sub-package** (if new domain): `pkg/client/<domain>/<domain>.go`
   - Define local `Doer` interface
   - Implement `Service` with methods matching API endpoints
2. **Add tests**: use `testutil.NewTestClient()` for route-based mocking
   or `testutil.NewTestClientWithURL()` with `httptest.Server` for complex logic
3. **Create command**: `internal/cli/cmd/<domain>/<domain>.go`
   - Use `client.New()` (or `client.NewAdmin()` for admin-only commands)
   - Instantiate sub-client: `svc := catalog.New(c)` (or `c.Catalog()` shorthand)
4. **Register in root.go**: `rootCmd.AddCommand(<domain>.NewCmd())`
5. **Run tests**: `go test ./...`

## Test Conventions

- Use `testutil.MockTransport` for simple request/response testing
- Use `httptest.NewServer` when you need request body assertions or complex routing
- Test file naming: `*_test.go` in the same package
- All tests must pass with `go test ./...` (no external dependencies)

## Output Formats

All list/get commands support `--output` (`-o`) flag:
- `table` (default) — human-readable columns
- `wide` — extra columns
- `yaml` — stoactl resource format
- `json` — raw API response
