# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Compare recorded webMethods and candidate route observations without network access."""

import argparse
import difflib
import json
import sys
from pathlib import Path


def project(record, headers):
    """Validate the capture and select only explicitly relevant HTTP headers."""
    if (
        not isinstance(record, dict)
        or not {"input", "response", "messages", "files"} <= record.keys()
    ):
        raise ValueError("capture requires input, response, messages and files")
    response = record["response"]
    if not isinstance(response, dict) or not {"body", "status", "headers"} <= response.keys():
        raise ValueError("response requires body, status and headers")
    if type(response["status"]) is not int or not 100 <= response["status"] <= 599:
        raise ValueError("status must be an HTTP status integer")
    if not isinstance(response["headers"], dict):
        raise ValueError("headers must be an object")
    normalized = {}
    for key, value in response["headers"].items():
        if not isinstance(value, (str, list)) or (
            isinstance(value, list) and not all(isinstance(item, str) for item in value)
        ):
            raise ValueError("header values must be strings or lists of strings")
        if key.lower() in normalized:
            raise ValueError("duplicate case-insensitive header")
        normalized[key.lower()] = value
    if not isinstance(record["messages"], list) or not isinstance(record["files"], dict):
        raise ValueError("messages must be an array and files an object")
    return {
        "input": record["input"],
        "response": {
            "body": response["body"],
            "status": response["status"],
            "headers": {key: normalized[key] for key in headers if key in normalized},
        },
        "messages": record["messages"],
        "files": record["files"],
    }


def compare(reference, candidate, headers):
    """Return a unified diff, preserving JSON types and array order."""
    if not isinstance(headers, list) or not all(isinstance(key, str) for key in headers):
        raise ValueError("headers selection must be an array of names")
    selected = sorted({key.lower() for key in headers})
    rendered = [
        json.dumps(project(record, selected), sort_keys=True, indent=2, allow_nan=False).splitlines(
            True
        )
        for record in (reference, candidate)
    ]
    return "".join(difflib.unified_diff(*rendered, fromfile="reference", tofile="candidate"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path, help="JSON case list; capture paths are relative to it")
    args = parser.parse_args()
    try:
        cases = load(args.suite)
        if not isinstance(cases, list) or not cases:
            raise ValueError("suite must be a non-empty case list")
        failed = False
        names = set()
        for case in cases:
            if (
                not isinstance(case, dict)
                or not {"name", "reference", "candidate", "headers"} <= case.keys()
            ):
                raise ValueError("case requires name, reference, candidate and headers")
            name = case["name"]
            if not isinstance(name, str) or not name or name in names:
                raise ValueError("case names must be unique non-empty strings")
            names.add(name)
            diff = compare(
                load(args.suite.parent / case["reference"]),
                load(args.suite.parent / case["candidate"]),
                case["headers"],
            )
            print(f"{'FAIL' if diff else 'PASS'} {name}")
            if diff:
                failed = True
                print(diff, end="")
        return int(failed)
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
