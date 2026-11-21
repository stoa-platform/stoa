# Legacy Python CLI (Archived Notice)

> **Status: Retired.** STOA has a single official CLI: **`stoactl`** (Go), maintained in [`stoa-go/`](../stoa-go/README.md).

This directory no longer ships an installable Python CLI package (`pyproject.toml` and source modules were retired when the CLI moved to Go).

## Use `stoactl` (Go)

Build `stoactl` from this repository:

```bash
go -C stoa-go build -o stoactl ./cmd/stoactl
./stoa-go/stoactl --help
```

See [`stoa-go/README.md`](../stoa-go/README.md) for commands, contexts, authentication, and development checks (`make test-cli`, `make lint-cli`).
