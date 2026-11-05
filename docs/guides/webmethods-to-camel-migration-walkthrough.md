# webMethods-to-Camel migration chain: demo walkthrough

> **Scope.** Synthetic, offline proof of concept. No webMethods Integration
> Server or Apache Camel runtime is started, no customer export is used, and
> nothing on this page demonstrates runtime parity or certifies a migration.

This walkthrough chains three scripts: route generation from synthetic flows,
the differential harness, and the campaign report. Each step lists how to
reproduce it and which file in the repository each statement comes from.

| Step | Script | Input | Output | Reference |
| --- | --- | --- | --- | --- |
| 1. Route generation | `scripts/migration_camel.py` | one synthetic flow XML | Camel XML routes on stdout | [migration-camel.md](../../scripts/migration-camel.md) |
| 2. Differential harness | `scripts/migration_differential.py` | JSON suite of reference/candidate captures | PASS/FAIL per case and a unified diff | [migration-differential.md](../../scripts/migration-differential.md) |
| 3. Campaign report | `scripts/migration_campaign.py` | directory of synthetic flow fixtures | `campaign.json` and `campaign.md` | [migration-campaign.md](../../scripts/migration-campaign.md) |

The campaign composes the first two steps: it imports `read_flow` and
`generate` from the generator and `compare` from the harness (top of
`scripts/migration_campaign.py`).

## Prerequisites

Run every command from the repository root with Python 3.11 or later. The three
scripts use the standard library only (`scripts/migration-camel.md`,
`scripts/migration-campaign.md`, imports of `scripts/migration_differential.py`);
the tests use `pytest`.

## Step 1: generate a Camel route from a synthetic flow

The fixtures in `scripts/tests/fixtures/camel/` are hand-written synthetic
samples in a strict webMethods-style profile: `FLOW NAME` holds one `SEQUENCE`
of `MAP` elements with `MAPSET FIELD="..." VALUE="..."` assignments to `body`
or `header.<name>` (`scripts/migration-camel.md`). They are not Integration
Server exports.

| Fixture | What it exercises |
| --- | --- |
| [constant.xml](../../scripts/tests/fixtures/camel/constant.xml) | one header assignment, then two ordered body overwrites with XML entities and surrounding whitespace |
| [empty.xml](../../scripts/tests/fixtures/camel/empty.xml) | an empty body constant and a header in the same `MAP` |
| [line-endings.xml](../../scripts/tests/fixtures/camel/line-endings.xml) | a CRLF body value and a header overwritten by a whitespace-padded value |

```sh
python3 scripts/migration_camel.py scripts/tests/fixtures/camel/constant.xml
python3 -m pytest scripts/tests/test_migration_camel.py -q
```

What to look for:

- Stdout is a deterministic Camel XML routes document whose entrypoint is
  `direct:<FLOW NAME>` (`scripts/migration-camel.md`).
- Each assignment becomes, in source order, a `setBody` or `setHeader` step
  holding a `constant` with `trim="false"` (`generate()` in
  `scripts/migration_camel.py`).
- Carriage returns are emitted as `&#13;` so CR and CRLF survive parsing of the
  output (`scripts/migration-camel.md`; covered by
  `test_carriage_returns_survive_xml_round_trip` in
  `scripts/tests/test_migration_camel.py`).
- Unsupported or unsafe input fails with exit code 2: unknown tags or
  attributes, DTDs, Camel property placeholders, resource constants, and files
  above 1,000,000 bytes (`scripts/migration-camel.md`; `LIMIT` in
  `scripts/migration_camel.py`; `test_rejects_unsupported_or_unsafe_input` and
  `test_size_limit` in `scripts/tests/test_migration_camel.py`).

## Step 2: compare captures with the differential harness

For each case of a JSON suite, the harness compares a reference capture with a
candidate capture, without contacting any host.

```sh
python3 scripts/migration_differential.py scripts/tests/fixtures/differential/suite.json
python3 -m pytest scripts/tests/test_migration_differential.py -q
```

- **Capture envelope.** `input`, a `response` with `body`, integer `status` and
  `headers`, an ordered `messages` array, and a `files` object
  (`scripts/migration-differential.md`).
- **Comparison rules.** Object key order is ignored; JSON types, array and
  message order, file names and contents are exact; header names are
  case-insensitive and only allowlisted headers are compared; input
  differences also fail (`scripts/migration-differential.md`).
- **Output.** `PASS <case>` or `FAIL <case>` followed by a unified
  reference/candidate diff. Exit code 0 means all equal, 1 any mismatch, 2 an
  invalid suite, capture or I/O error (`scripts/migration-differential.md`).
- **Expected sample result.** The bundled
  [reference](../../scripts/tests/fixtures/differential/reference.json) and
  [candidate](../../scripts/tests/fixtures/differential/candidate.json) are
  identical synthetic captures, so the sample prints `PASS order-created` and
  exits 0 (`test_sample_cli` in `scripts/tests/test_migration_differential.py`).
  They are not captures from either runtime.
- **Seeing a FAIL.** Copy the fixture directory to a temporary location, change
  one value in the copied `candidate.json`, and run the harness on the copied
  `suite.json`. `test_each_observable_diff` and
  `test_cli_mismatch_and_invalid_input` in
  `scripts/tests/test_migration_differential.py` exercise the same paths.

## Step 3: run the campaign and read the report

```sh
python3 scripts/migration_campaign.py --output /tmp/stoa-migration-campaign
python3 -m pytest scripts/tests/test_migration_campaign.py -q
```

For every `*.xml` fixture under `scripts/tests/fixtures/camel`, in sorted path
order (override with `--fixtures PATH`), the campaign
(`scripts/migration-campaign.md`, `run()` in `scripts/migration_campaign.py`):

1. reads the source flow and generates Camel XML with the Step 1 generator;
2. reads the constants back from the generated XML, independently of the source
   reader (`candidate_assignments()`);
3. builds a synthetic envelope for each side: empty input, initially empty
   body, status 200, no messages or files, all assigned headers selected
   (`capture()`);
4. compares the source assignments (reference) with the generated ones
   (candidate) using the Step 2 comparator.

Reports are written to the `--output` directory and overwritten on each run
(`scripts/migration-campaign.md`):

- `campaign.md`: a summary table (flow, result, generation and comparison
  seconds) and one explanation section per flow, with the diff when outputs
  differ. It is also printed to stdout.
- `campaign.json`: for each flow, the relative fixture path, generated route
  XML, `PASS`/`FAIL`/`ERROR`, explanation, unified diff, `generation_seconds`
  and `comparison_seconds`.

Exit code 0 means all flows match, 1 differences, 2 invalid fixtures or I/O
errors; a per-flow error does not stop the remaining flows
(`scripts/migration-campaign.md`).

On the committed fixtures, every flow is expected to `PASS` with an empty diff;
`test_all_flows_and_measurements` in `scripts/tests/test_migration_campaign.py`
asserts this. `test_changed_generated_constant_is_explained` in the same file
shows the FAIL path: it alters one generated header constant and checks that
the report carries the diff and the explanation.

## Where the measured results come from

- No measured result is stored in the repository. Durations are measured on
  each run with `time.perf_counter()` around the local generation step and the
  comparison step (envelope construction and diffing, report writing excluded),
  then written to `campaign.json` and `campaign.md` in the chosen output
  directory (`scripts/migration-campaign.md`; `run()` in
  `scripts/migration_campaign.py`).
- An attempted step that fails is still timed; a comparison that did not run is
  `null` in JSON and `-` in Markdown (`scripts/migration-campaign.md`).
- Measurements vary by machine and run. The tests only check that durations
  are non-negative; there is no timing threshold
  (`scripts/tests/test_migration_campaign.py`). Treat timings as local
  observations, not performance figures.
- Result labels come from the run itself: `ERROR` when reading, generation or
  read-back raises, otherwise `PASS` or `FAIL` from the comparator diff
  (`run()` in `scripts/migration_campaign.py`).

To show results in a demo, run the campaign live, or share the generated
`campaign.md` together with the commit SHA and the machine it was produced on.

## What this shows, and what it does not

It shows:

- deterministic translation of the supported constant-assignment profile into
  Camel XML route definitions;
- an offline comparator with an explicit capture contract and diff output;
- a reproducible campaign that ties both together and reports per-flow results
  and local timings.

It does not show (`scripts/migration-camel.md`,
`scripts/migration-differential.md`, `scripts/migration-campaign.md`):

- execution on a Camel or webMethods runtime, route connectivity, HTTP status
  handling or side-effect collection;
- support for real Integration Server export dialects, `INVOKE`, `BRANCH` or
  `LOOP` steps, variable mapping, error handling or connector bindings;
- runtime parity, migration correctness on real flows, or any certification.

Only synthetic samples may be committed to these fixture directories; do not
use customer exports (`scripts/migration-camel.md`).

## Provenance

The generator, the differential harness, the campaign script with its fixtures
and tests, and this walkthrough were produced with AI assistance under the
repository [AI usage policy](../../CONTRIBUTING.md#ai-usage-policy). The
generator and harness changes each received an independent automated review
before merge; the campaign change received one before its pull request was
opened. Under that policy, AI output is a draft, human verification
is required before merge, and completed human verification is recorded only
through a `Human-Verified-By` commit trailer. This page claims no human
verification beyond what the commit history records.
