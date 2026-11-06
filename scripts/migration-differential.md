# Offline migration differential harness

Run from the repository root with Python 3.11+:

```sh
python3 scripts/migration_differential.py scripts/tests/fixtures/differential/suite.json
python3 -m pytest scripts/tests/test_migration_differential.py -q
ruff check scripts/migration_differential.py scripts/tests/test_migration_differential.py
```

This is the comparator core for the webMethods-to-Camel POC. The
[Camel generator](migration-camel.md) and [offline campaign](migration-campaign.md)
exercise synthetic constant assignments; no runtime execution adapter is included.
The sample is synthetic, not a capture from either runtime and not migration proof.
It demonstrates the recorded-fixture fallback, without contacting any host.

A suite is a non-empty JSON array of uniquely named cases. Each case specifies
`reference` and `candidate` capture paths (relative to the suite), and an explicit
`headers` allowlist. Both captures must contain the same `input`, plus a
`response` with `body`, integer `status` and `headers`, an ordered `messages`
array, and a `files` object mapping emitted paths to contents. Empty collections
mean no side effects; missing collections are invalid. See the sample for shape.

Future execution adapters must replay each case's identical input against both
runtimes in isolation and record all emitted messages/files in this envelope.
Use strings for text bodies; encode binary bodies/files as base64 strings in
both captures. Message entries should include destination, payload and relevant
metadata. The comparator trusts capture completeness; it does not observe I/O.

Object key order is ignored; JSON types, array/message order, file names and
contents are exact. Header names are case-insensitive, values are exact (lists
retain repeated values). Unselected HTTP headers are ignored. No timestamps or
IDs are silently removed; normalize nondeterministic fields in capture adapters
only under an explicitly agreed contract. Input differences also fail.

Stdout contains PASS/FAIL per case and a unified reference/candidate JSON diff.
Exit codes: 0 = all equal, 1 = any mismatch, 2 = invalid suite/capture or I/O error.
Redirect stdout to retain the report. Reports contain captured data; use only
sanitized fixtures. Remaining work: real captures, runtime execution,
side-effect collectors, broader flow coverage and CI integration.
