# Agent Roles PoC (First Slice)

Autonomous local Docker Compose proof of concept for `stoa-gateway` agent roles, sender-constrained tokens, gateway-native delegation, signed role policies, and bounded atomic admission.

## Purpose

This first slice exercises the core gateway security controls without an external IdP or Control Plane HTTP service:

- **Local RS256 validator**: dedicated to `/mcp/poc/*` and strictly separate from the OIDC JWT validator, with mandatory `kid`, strict RS256 verification, and a boot-ephemeral keypair that is never exported.
- **DPoP sender-constrained tokens**: verifies `htm`, `htu` (component-normalized), `ath`, and `cnf.jkt` with a bounded atomic `jti` anti-replay table.
- **Gateway-native delegation (`POST /mcp/poc/delegate`)**: mints narrowed child tokens with `iss=stoa-poc-delegation`, canonical tool audience `mcp-tool:<tenant>:<tool>`, `act`, `chain_id`, `jti`, `parent_jti`, `depth <= 3`, `exp <= parent.exp`, and inherited non-empty tenant.
- **Signed role policies (`stoa-agent-role-policy+jws`)**: EdDSA-verified against a pinned local JWKS trust file, maximum 15-minute validity, durable `0600` atomic anti-rollback version floor, monotonic session anti-widening, and deterministic v1 argument constraints (`allowed_values`, `prefix`, exact-domain `max_number`).
- **Two-level atomic budgets and chain revocation (`POST /mcp/poc/revoke`)**: all-or-nothing per-chain and per-root-caller budget debits, bounded admission and revocation tables (fail-closed when full), and guarded sequential sub-calls (`poc/subcalls`).

## Topology

The Compose stack runs 4 containers across 2 isolated internal bridge networks with no published host ports and `/admin/*` routes disabled (`STOA_ADMIN_ROUTES_DISABLED=true`):

| Service | Networks | Role |
| --- | --- | --- |
| `stoa-gateway` | `mcp-net`, `upstream-net` | Autonomous gateway serving `/ready` and `/mcp/poc*` |
| `agent-parent` | `mcp-net` | Root agent container holding the bootstrap secret |
| `agent-child` | `mcp-net` | Delegated agent container (no bootstrap secret) |
| `upstream-mock` | `upstream-net` | Isolated backend mock unreachable from agent containers |

Both `mcp-net` and `upstream-net` are configured with `internal: true`.

## Prerequisites

- Docker with Compose v2
- Python 3.12 with `cryptography==46.0.3` (used by `scripts/gen_fixtures.py`)

## Running the Verification Scenarios

Run each script from `deploy/poc-roles-agents`:

```bash
bash scripts/run_jalon1.sh
bash scripts/run_jalon2.sh
bash scripts/run_jalon3.sh
bash scripts/run_jalon5_floor.sh
```

What each scenario verifies:

- **`scripts/run_jalon1.sh`**: Ephemeral fixture generation, `/ready` gating, disabled `/admin/*`, network isolation between agents and `upstream-mock`, `POST /mcp/poc/bootstrap`, DPoP proof validation and replay rejection, and backend API key injection without forwarding caller tokens upstream.
- **`scripts/run_jalon2.sh`**: Signed role policy loading with a `0600` anti-rollback floor file, gateway delegation (`POST /mcp/poc/delegate`) up to depth 3 (rejecting depth 4), v1 argument constraints, strict child narrowing, caller limits, role changes under the same token, OPA enforcement, outbound address policy enforcement, and refusal to follow 3xx redirects.
- **`scripts/run_jalon3.sh`**: Filtered `tools/list`, guarded sequential sub-calls (`poc/subcalls`) with full authorization on fallback steps, atomic chain revocation (`POST /mcp/poc/revoke`), two-level budgets (chain + root caller) under concurrency, and token invalidation across a gateway restart.
- **`scripts/run_jalon5_floor.sh`**: Durable `0600` anti-rollback floor persistence in the named `role-floors` volume across restarts, `SIGKILL`, and container recreation, plus fail-closed startup when a lower version is presented or the floor file is unreadable.

The [refusal catalogue](cas/README.md) maps the 12 checks to their requests, exact responses, and gateway code. GitHub Actions runs the scenarios for matching pull requests and on each push to `main`. A failed scenario fails the Compose check.

## Caller limits

To read the current session's limits, send this JSON-RPC request to `POST /mcp/poc` with the session's DPoP token and a fresh proof.

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"stoa_security","arguments":{"action":"get_my_limits"}}}
```

The result includes `structuredContent` and the same JSON as text content. It reports the role from the signed token, the issued and current policy versions, the canonical names of the effective tools, and their argument constraints. A child sees only its resource-scoped grant and the introspection tool. Each argument's array lists rules that must all match. A number subject to `max_number` must be finite and within the gateway's exact numeric domain.

Introspection requires an active chain and returns remaining chain and caller budgets without debiting either. The response uses `Cache-Control: no-store`. Calls are checked against the policies and budgets in effect when they arrive.

## Restart Behavior

- The gateway generates its local RS256 signing keypair in memory on boot and never writes it to disk. All tokens minted before a `stoa-gateway` restart are immediately rejected after restart.
- In-memory admission state (active chains, chain/caller budgets, revocation table, and DPoP replay table) resets when the gateway process restarts.
- The anti-rollback policy floor is stored in `/tmp/stoa-poc-floors` backed by the named Compose volume `role-floors` (`0600`). It persists across restarts and container recreation until `docker compose down -v` removes the volume.

## Ephemeral Keys and Fixtures

All keys and secrets used by these scripts—Ed25519 policy signing keys, per-agent EC P-256 DPoP keys, bootstrap secrets, and mock upstream API keys—are ephemeral and generated fresh for each run. The policy signing private key stays in memory during fixture generation and is never written to disk.
