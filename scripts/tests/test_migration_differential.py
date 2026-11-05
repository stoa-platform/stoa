# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Offline differential contract and CLI regression tests."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.migration_differential import compare

FIXTURES = Path(__file__).parent / "fixtures/differential"
SCRIPT = Path(__file__).parents[1] / "migration_differential.py"


def snapshot():
    return json.loads((FIXTURES / "reference.json").read_text())


def test_header_case_and_unselected_values():
    reference = snapshot()
    candidate = copy.deepcopy(reference)
    candidate["response"]["headers"] = {"CONTENT-TYPE": "application/json", "Date": "later"}
    assert compare(reference, candidate, ["Content-Type"]) == ""


@pytest.mark.parametrize("field", ["body", "status", "headers", "messages", "files", "input"])
def test_each_observable_diff(field):
    reference = snapshot()
    candidate = copy.deepcopy(reference)
    if field in {"body", "status", "headers"}:
        candidate["response"][field] = {
            "body": {"accepted": False},
            "status": 500,
            "headers": {"content-type": "text/plain"},
        }[field]
    elif field == "input":
        candidate[field] = {"order_id": "different"}
    elif field == "messages":
        candidate[field] = []
    else:
        candidate[field] = {"orders/order-1.txt": "changed"}
    diff = compare(reference, candidate, ["content-type"])
    assert "--- reference" in diff and "+++ candidate" in diff
    assert field in diff


def test_json_types_are_distinct():
    candidate = snapshot()
    candidate["response"]["body"]["accepted"] = 1
    assert compare(snapshot(), candidate, [])


@pytest.mark.parametrize("mutation", ["missing", "status", "duplicate_header", "messages"])
def test_invalid_capture_rejected(mutation):
    candidate = snapshot()
    if mutation == "missing":
        del candidate["files"]
    elif mutation == "status":
        candidate["response"]["status"] = True
    elif mutation == "messages":
        candidate["messages"] = {}
    else:
        candidate["response"]["headers"]["Content-Type"] = "application/json"
    with pytest.raises(ValueError):
        compare(snapshot(), candidate, [])


def run_cli(suite):
    return subprocess.run([sys.executable, str(SCRIPT), str(suite)], capture_output=True, text=True)


def test_sample_cli():
    result = run_cli(FIXTURES / "suite.json")
    assert result.returncode == 0
    assert "PASS order-created" in result.stdout


def test_cli_mismatch_and_invalid_input(tmp_path):
    candidate = snapshot()
    candidate["messages"] = []
    (tmp_path / "candidate.json").write_text(json.dumps(candidate))
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            [
                {
                    "name": "changed",
                    "reference": str(FIXTURES.resolve() / "reference.json"),
                    "candidate": "candidate.json",
                    "headers": ["content-type"],
                }
            ]
        )
    )
    result = run_cli(suite)
    assert result.returncode == 1 and "FAIL changed" in result.stdout
    suite.write_text("[]")
    assert run_cli(suite).returncode == 2
    suite.write_text("invalid json")
    assert run_cli(suite).returncode == 2
