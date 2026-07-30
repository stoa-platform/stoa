# Codex prompt — P0-AUD-2 PR 2 (Gateway: durable WAL audit spool)

You are implementing **PR 2 of P0-AUD-2** in the STOA monorepo
(`/Users/torpedo/hlfh-repos/stoa`), component `stoa-gateway/` (Rust, Tokio).

Read first: the sibling `p0-aud-2-README.md` and
`adrs-drafts/adr-070-gateway-fail-closed-posture.md` §4.6 — **the five
mandatory spool semantics are the spec.** Follow the branch/commit/clippy/test
conventions from `p0-mcp-1-pr2-gateway.md`. This PR is the **storage layer
only** — no CP client, no `tools/call` wiring (that is PR 3). It is fully
standalone and unit-testable.

## Goal

A durable, crash-safe, bounded on-disk write-ahead-log spool for audit events
the gateway has not yet shipped to CP-API. ADR-070 §4.6 forbids an in-memory
drop-on-overflow buffer for the in-scope critical events.

## Branch / ticket

`feat/cab-2227-aud-2-gateway-audit-spool` off fresh `origin/main`. First commit
subject carries `CAB-2227`. Scope `gateway`. `cargo clippy --all-targets -D
warnings` clean; `cargo test` (not `--all-features`).

## Scope — new module `stoa-gateway/src/audit/`

### `audit/event.rs`

- `struct AuditEvent` — the in-scope payload: `event_type`, `decision`
  (`Allow`/`Deny`), `reason`, `tenant_id`, `actor_id: Option`, `session_id`,
  `resource_type`, `resource_id`, `tool_call_id`, `approval_id: Option`,
  `policy_version: Option`, `correlation_id`, `occurred_at`. `serde`
  Serialize/Deserialize — the wire shape must match PR 1's frozen request
  schema. Each event carries a stable `idempotency_key` (uuid) generated at
  enqueue time.

### `audit/spool.rs` — the WAL spool

ADR-070 §4.6 semantics 1, 2, 3:

- **Append-only segments.** A bounded directory of rotated segment files
  (e.g. `00000001.seg`); each line is one length-prefixed or newline-delimited
  JSON event. Rotate at a configurable segment size. `fsync` on append (or
  batched fsync with a documented bound) so a process restart loses nothing.
- **`append(&self, event) -> Result<(), SpoolError>`** — appends durably.
- **`drain_oldest(&self, max: usize) -> Vec<(SpoolCursor, AuditEvent)>`** and
  **`ack(&self, cursor)`** — read oldest-first without removing; remove a
  segment only once every event in it is acked (replay safety for PR 3).
- **Bounded growth.** Configurable capacity (bytes or event count). Expose
  `depth()`, `oldest_age()`, `is_over_high_water()` (default high-water = 80%
  of capacity). The readiness coupling itself is wired in PR 3 — this PR only
  exposes the predicate.
- **No silent drop.** When the spool genuinely cannot accept (disk full, write
  error, segment corruption on read), `append` returns `SpoolError::GapDeclared`
  — the caller (PR 3) turns that into the `audit_gap_declared` incident +
  fail-closed. The spool never drops an event silently and never returns `Ok`
  on a failed durable write.
- **Crash recovery.** On construction, scan the segment directory, validate
  each segment, skip/quarantine a corrupt trailing record (partial write from a
  crash) but surface earlier corruption as `GapDeclared`. Recovered events are
  immediately drainable in original order.

### `audit/mod.rs`

Re-export; add `pub mod audit;` to `src/lib.rs`.

### Config

Add to `config`: `audit_spool_dir` (path), `audit_spool_capacity_bytes`,
`audit_spool_segment_bytes`, `audit_spool_high_water_pct` (default 80).

## Tests — `#[cfg(test)] mod tests`, test-first, red-before-green

Rust regression tests named `fn regression_*` + `// regression for CAB-2227`.
Use `tempfile::tempdir()` for spool directories — real files, not mocks.

- `regression_audit_spool_survives_process_restart` — append N, drop the spool
  struct, reconstruct from the same dir, drain → all N present, in order.
- `regression_audit_spool_drain_is_oldest_first`.
- `regression_audit_spool_segment_removed_only_after_all_acked`.
- `regression_audit_spool_reports_over_high_water_at_threshold`.
- `regression_audit_spool_append_fails_loud_when_capacity_exhausted` — over
  hard capacity → `SpoolError::GapDeclared`, never silent `Ok`.
- `regression_audit_spool_recovers_partial_trailing_record` — hand-write a
  truncated last line, reconstruct → earlier events intact, no panic.
- `regression_audit_event_wire_shape_matches_cp_schema` — serialize an
  `AuditEvent`, assert the JSON keys equal PR 1's frozen request schema.

## Constraints

- **PR ≤ 300 LOC**; if exceeded split (`event.rs` + spool append/segments /
  recovery + bounded-growth + tests).
- `cargo fmt --check`, `clippy --all-targets -D warnings`, `cargo test` clean.
- gateway coverage gate — do not lower it.
- No new heavy deps if the std lib + existing crates suffice; if a WAL crate is
  proposed, justify it in the PR description.

## Deliverable

Draft PR to `main`, body `Linear: [CAB-2227]`. Report the final insertion
count and the public API surface of `audit::spool` (PR 3 consumes it).
