# Agent Roles Demo (Preview)

> **Status: Preview.** Local, self-contained proof of concept running `stoa-gateway`, a simulated refund backend, and isolated agent containers over Docker Compose. No external IdP, no cloud account, and no provider API key required.

## What this demo proves

1. **Key-free agents:** neither agent container receives the upstream API key. `stoa-gateway` injects the backend credential on allowed calls and the upstream mock verifies `caller_auth_headers_seen=0`.
2. **Signed role with argument cap:** a parent agent bootstraps an Ed25519-signed `refund_operator` role (500 EUR cap) and delegates a narrower child token (`refunds_create`, `customer_id=C-1042`, **50 EUR cap**).
3. **Auditable refusal with `decision_id`:**
   - `50 EUR` for `C-1042` → **allowed**, executed once by the simulated backend.
   - `80 EUR` for `C-1042` → **refused** (`argument_constraint_denied`, `limit_eur=50`), returning a `decision_id` matched by exact UUID equality against the exported NDJSON journal (`decisions.ndjson`), with zero upstream execution.
   - `50 EUR` for `C-2077` → **refused** (`customer_outside_scope`), matched in the journal.
   - Parent revokes the chain → child retry `50 EUR` for `C-1042` → **refused** (`chain_revoked`), matched in the journal.
4. **Clean isolation:** each run creates an isolated Compose project, ephemeral fixtures, and temporary local images, then removes containers, volumes, and local images on exit.

## Prerequisites

- Docker Engine + Docker Compose v2
- `make`, `python3`, `openssl`

## Run it

From the repository root (or from `examples/agent-roles/`):

```bash
make demo
```

**Cold fresh-clone measurement (no Docker or Go cache):** **1 command** inside
the clone (`make demo`; 3 commands from scratch with `git clone` and `cd`) and
**155.9 s** to the first refusal (`80 EUR` denied at the `50 EUR` cap, verified
against `decisions.ndjson`, including the uncached Docker build of `stoa-gateway`).

## Known limits (Preview)

- Simulated refunds against a local mock backend (`upstream_mock.py`).
- Chain and root-caller budgets live in gateway memory and reset on gateway restart.
- Local no-IdP bootstrap is for evaluation only; production deployments authenticate behind an enterprise IdP (see [`quickstart/`](../../quickstart/README.md) and [`docs/platform.md`](../../docs/platform.md)).
- Full operator scripts, rotation proofs, relay dock tests, and interactive Claude Code scenarios are documented in [`OPERATOR.md`](OPERATOR.md).
