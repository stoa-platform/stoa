<div align="center">
  <h1>🚀 stoactl</h1>
  <p><strong>GitOps-native CLI for STOA Platform</strong></p>
  <p>
    <a href="https://github.com/stoa-platform/stoactl/releases">
      <img src="https://img.shields.io/github/v/release/stoa-platform/stoactl?style=flat-square" alt="Release">
    </a>
    <a href="LICENSE">
      <img src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" alt="License">
    </a>
    <a href="https://goreportcard.com/report/github.com/stoa-platform/stoactl">
      <img src="https://goreportcard.com/badge/github.com/stoa-platform/stoactl?style=flat-square" alt="Go Report Card">
    </a>
  </p>
</div>

---

`stoactl` is a command-line interface for [STOA Platform](https://gostoa.dev) — The European Agent Gateway. It provides a declarative, kubectl-like experience for managing APIs, subscriptions, and other STOA resources through infrastructure-as-code patterns.

## Features

- **GitOps-native**: Declarative resource management with `apply` and `delete`
- **Multi-context**: Manage multiple STOA environments (dev, staging, prod)
- **OAuth2/OIDC**: Secure authentication via Keycloak
- **Familiar UX**: kubectl-style commands for a seamless developer experience

## Installation

### Homebrew (macOS/Linux)

```bash
brew install stoa-platform/tap/stoactl
```

### Binary (Linux/macOS)

```bash
## See GitHub Releases for binary downloads:
## https://github.com/stoa-platform/stoactl/releases
```

### Docker

```bash
docker run ghcr.io/stoa-platform/stoactl:latest version
```

### From Source

```bash
go install github.com/stoa-platform/stoactl/cmd/stoactl@latest
```

## Quick Start

### 1. Configure a context

```bash
stoactl config set-context prod \
  --server=https://api.gostoa.dev \
  --tenant=acme
```

### 2. Switch to the context

```bash
stoactl config use-context prod
```

### 3. Authenticate

```bash
stoactl auth login
```

### 4. List resources

```bash
stoactl get apis
stoactl get subscriptions
```

### 5. Apply resources

```yaml
# api.yaml
apiVersion: stoa.dev/v1
kind: API
metadata:
  name: payment-api
  tenant: acme
spec:
  upstream: https://api.payments.example.com
  path: /payments
  version: v1
```

```bash
stoactl apply -f api.yaml
```

## Commands

| Command | Description |
|---------|-------------|
| `stoactl config set-context` | Create or update a context |
| `stoactl config use-context` | Switch to a context |
| `stoactl config get-contexts` | List all contexts |
| `stoactl auth login` | Authenticate with STOA |
| `stoactl auth status` | Show authentication status |
| `stoactl get <resource>` | List resources |
| `stoactl apply -f <file>` | Create or update resources |
| `stoactl delete <resource> <name>` | Delete a resource |
| `stoactl version` | Print version information |

## Scoping flags: `--tenant` vs `--namespace`

`stoactl` exposes two **distinct** scoping flags. They look similar but mean
different things and live at different layers (CAB-2117).

| Flag | Scope | Where it applies |
|------|-------|------------------|
| `--tenant` (or `STOACTL_TENANT`) | CP tenant — sets `X-Tenant-ID` and tenant-scoped paths on the admin API | Persistent root flag, inherited by every subcommand |
| `--namespace` (or `STOACTL_NAMESPACE`) on `stoactl bridge` | Kubernetes namespace written to `metadata.namespace` of generated Tool CRDs | `stoactl bridge` only |
| `--namespace` (or `STOACTL_NAMESPACE`) on every other command | **Deprecated** legacy alias for `--tenant`; emits a stderr warning and will be removed in the next breaking release | All non-`bridge` commands |

### Canonical two-scope example

```bash
stoactl bridge openapi.yaml \
  --namespace stoa-demo \   # K8s namespace → metadata.namespace of CRDs
  --tenant demo \           # CP tenant → admin-API scope for --apply
  --apply
```

The two scopes coexist without conflict: `metadata.namespace=stoa-demo` ends
up on the generated Tool CRDs, while `POST /v1/admin/mcp/servers` runs under
`tenant=demo`.

### Migration plan

* **This release (N)** — `--tenant` introduced everywhere; `--namespace` on
  non-bridge commands keeps working but emits this warning on stderr:
  ```
  --namespace is deprecated for tenant scope on 'stoactl <cmd>', use --tenant
  ```
* **Next breaking release (N+1)** — `--namespace` is removed from
  non-`bridge` commands; using it will exit with an explicit error pointing
  to `--tenant`. `stoactl bridge --namespace` keeps its K8s meaning
  unchanged.

## Configuration

stoactl stores configuration in `~/.stoactl/config.yaml`:

```yaml
current-context: prod
contexts:
  prod:
    server: https://api.gostoa.dev
    tenant: acme
  dev:
    server: https://api.dev.gostoa.dev
    tenant: acme-dev
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Command misuse |
| 3 | Authentication failed |
| 4 | Resource not found |
| 5 | Conflict |
| 6 | Validation error |

## Related Projects

| Repository | Description |
|------------|-------------|
| [stoa](https://github.com/stoa-platform/stoa) | Main platform monorepo |
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Documentation |
| [stoa-helm](https://github.com/stoa-platform/stoa-helm) | Helm charts |

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a Pull Request.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

---

<div align="center">
  <p>Part of the <a href="https://github.com/stoa-platform">STOA Platform</a> project</p>
  <p>🇪🇺 Built in Europe for European sovereignty</p>
</div>
