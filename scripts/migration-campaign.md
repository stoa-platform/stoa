# Reproducible synthetic migration campaign

Run from the repository root with Python 3.11+ (standard library only):

```sh
python3 scripts/migration_campaign.py --output /tmp/stoa-migration-campaign
python3 -m pytest scripts/tests -q
ruff check scripts/migration_campaign.py scripts/tests/test_migration_campaign.py
```

The campaign recursively discovers every `*.xml` fixture under
`scripts/tests/fixtures/camel` in sorted path order. Override this directory with
`--fixtures PATH`, using only synthetic flows in the supported
[constant-assignment profile](migration-camel.md). The fixtures cover ordered
body overwrites, empty strings, header overwrites, whitespace and CRLF escaping.

For each flow, the campaign reads the source and generates Camel XML, then
independently reads the generated constants and calls the existing
[differential comparator](migration-differential.md). Both sides use a synthetic
envelope with empty input, initial empty body, status 200, no messages or files,
and all assigned headers selected. The source assignments define the reference;
the generated XML defines the candidate. This checks final constant-assignment
translation fidelity only. It does not execute either runtime, verify route
connectivity or prove runtime parity, status handling or side-effect collection.

`campaign.json` contains each relative fixture path, generated XML, PASS/FAIL/ERROR,
explanation, unified diff and measured `generation_seconds` / `comparison_seconds`.
`campaign.md` contains the summary and explained differences and is also printed
to stdout. Each duration uses `time.perf_counter()` around the actual local step;
comparison includes envelope construction and diffing, but report writing is
excluded. An attempted failing step is timed; an unattempted comparison is null
in JSON and `-` in Markdown. Measurements vary by machine and run; reproduce
them with the command above. No timing threshold is used by the tests.

Exit codes: 0 for all matches, 1 for differences, 2 for invalid fixtures or I/O
errors. Per-flow errors do not prevent remaining fixtures from running. An empty
fixture directory is an error. Output files are overwritten on each run.
