# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Measure offline synthetic flow generation and translation comparisons."""

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__:
    from .migration_camel import generate, read_flow
    from .migration_differential import compare
else:
    from migration_camel import generate, read_flow
    from migration_differential import compare

FIXTURES = Path(__file__).parent / "tests/fixtures/camel"
NS = "{http://camel.apache.org/schema/spring}"


def capture(assignments):
    """Model constant assignments only; the envelope is synthetic, not observed I/O."""
    response = {"body": "", "status": 200, "headers": {}}
    for field, value in assignments:
        if field == "body":
            response["body"] = value
        else:
            response["headers"][field[7:]] = value
    return {"input": {}, "response": response, "messages": [], "files": {}}


def candidate_assignments(xml):
    """Read the generated constant-only subset independently of the source reader."""
    route = ET.fromstring(xml).find(f"{NS}route")
    if route is None:
        raise ValueError("Missing generated route")
    for step in list(route)[1:]:
        if step.tag not in {f"{NS}setBody", f"{NS}setHeader"}:
            raise ValueError("Unsupported generated step")
        constant = step.find(f"{NS}constant")
        if constant is None or constant.get("trim") != "false":
            raise ValueError("Expected an untrimmed generated constant")
        field = "body" if step.tag == f"{NS}setBody" else "header." + step.attrib["name"]
        yield field, constant.text or ""


def run(fixtures):
    paths = sorted(fixtures.rglob("*.xml"))
    if not paths:
        raise ValueError("No XML flow fixtures found")
    rows = []
    for path in paths:
        row = {
            "flow": path.relative_to(fixtures).as_posix(),
            "result": "ERROR",
            "diff": "",
            "generation_seconds": None,
            "comparison_seconds": None,
            "route_xml": "",
        }
        stage = "generation_seconds"
        started = time.perf_counter()
        try:
            flow = read_flow(path)
            row["route_xml"] = generate(flow)
            row[stage] = time.perf_counter() - started
            stage = "comparison_seconds"
            started = time.perf_counter()
            reference = capture(flow.assignments)
            candidate = capture(candidate_assignments(row["route_xml"]))
            headers = sorted(
                set(reference["response"]["headers"]) | set(candidate["response"]["headers"])
            )
            row["diff"] = compare(reference, candidate, headers)
            row["result"] = "FAIL" if row["diff"] else "PASS"
            row["explanation"] = (
                "Constant assignment outputs differ; see reference/candidate diff."
                if row["diff"]
                else "Constant assignment outputs match in the offline model."
            )
        except (OSError, ValueError, KeyError, ET.ParseError) as error:
            row["explanation"] = str(error)
        finally:
            row[stage] = time.perf_counter() - started
        rows.append(row)
    return rows


def markdown(rows):
    lines = [
        "# Synthetic migration campaign",
        "",
        "Offline constant-assignment model only; no Camel/webMethods runtime was executed.",
        "Times are measured wall-clock seconds; '-' means the step did not run.",
        "",
        "| Flow | Result | Generation (s) | Comparison (s) |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in rows:
        times = [
            "-" if row[key] is None else f"{row[key]:.9f}"
            for key in ("generation_seconds", "comparison_seconds")
        ]
        lines.append(f"| {row['flow']} | {row['result']} | {' | '.join(times)} |")
    for row in rows:
        lines.extend(["", f"## {row['flow']}", "", row["explanation"]])
        if row["diff"]:
            lines.extend(["", "```diff", row["diff"].rstrip(), "```"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = run(args.fixtures)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "campaign.json").write_text(
            json.dumps(rows, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        summary = markdown(rows)
        (args.output / "campaign.md").write_text(summary, encoding="utf-8")
        print(summary, end="")
        return (
            2
            if any(row["result"] == "ERROR" for row in rows)
            else int(any(row["result"] == "FAIL" for row in rows))
        )
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
