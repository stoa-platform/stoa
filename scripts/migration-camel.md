# Synthetic flow to Camel XML

Run locally from the repository root (Python 3.11+, no runtime dependencies):

```sh
python3 scripts/migration_camel.py scripts/tests/fixtures/camel/constant.xml
python3 -m pytest scripts/tests/test_migration_camel.py -q
ruff check scripts/migration_camel.py scripts/tests/test_migration_camel.py
```

This bounded POC accepts a **synthetic webMethods-style profile**, not arbitrary
Integration Server exports. `FLOW NAME` contains exactly one `SEQUENCE`, holding
nonempty `MAP` elements with nonempty `MAPSET FIELD="..." VALUE="..."` assignments.
Supported string fields are `body` and `header.<name>`. Names match
`[A-Za-z_][A-Za-z0-9_.-]*`. Assignments retain order; later assignments overwrite
earlier ones. XML entities are decoded and output is XML-escaped. Constants use
`trim="false"`; whitespace in values follows XML attribute normalization rules.
Carriage returns decoded from character references are emitted as `&#13;`,
preserving CR and CRLF in body and header constants when the output is parsed.
Unknown tags/attributes, mixed text, empty sequences, nested assignments, DTDs,
non-UTF-8 input and files above 1,000,000 bytes fail. Camel property placeholders
and resource constants are rejected to avoid load-time interpolation or I/O.

Stdout is a deterministic Camel XML routes document with entrypoint
`direct:<FLOW NAME>`; exit codes are 0 on success and 2 on invalid input or I/O.
No runtime is launched. The generated route only changes body/headers and has no
external endpoint. It requires Camel core/direct and an XML route loader.
The XML mapping follows Apache Camel's [constant expression documentation](https://camel.apache.org/components/4.18.x/languages/constant-language.html).

This script sits beside `migration_differential.py` (parallel work), without
changing its capture contract. A future execution adapter must feed identical
inputs to both runtimes and record that harness's input/response/messages/files
envelope. Generated XML is not a response capture or proof of runtime parity.
Remaining: actual export dialect validation, INVOKE/BRANCH/LOOP, variable mapping,
error handling, connector bindings, Camel runtime tests and differential replay.
Only synthetic samples may be committed. Do not use customer exports here.
