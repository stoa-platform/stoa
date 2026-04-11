# Bats Tests

Bash unit tests for shell scripts in `scripts/`, using [bats-core](https://bats-core.readthedocs.io/).

## Install

```bash
# macOS
brew install bats-core

# Ubuntu / CI
sudo apt-get install -y bats
```

## Run

```bash
# All bats tests
bats tests/bats/

# Single file
bats tests/bats/council-review.bats
```

## Suites

| File | Covers |
|------|--------|
| `council-review.bats` | `scripts/council-review.sh` helpers (CAB-2047): `aggregate_scores`, `sum_usage_tokens`, `compute_cost_eur` |

## Conventions

- Each `.bats` file sources the script under test. Scripts must guard their entrypoint
  with `[[ "${BASH_SOURCE[0]}" == "${0}" ]] && main "$@"` so sourcing does not run `main`.
- Use `setup()` / `teardown()` to create and clean up per-test tmpdirs.
- Helpers for fixture construction belong at the top of the file.
- No network calls — fixtures only. For Anthropic/Linear-backed scripts, use `MOCK_API=1`.

See `.claude/rules/council-s3.md` for the Council S3 specification.
