"""Unit tests for scripts/ci/parse_council_report.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from parse_council_report import (
    _concat_assistant_text,
    _extract_estimate_points,
    _extract_mode,
    _extract_score_regex,
    main,
    parse_text,
    run,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parent.parent / "parse_council_report.py"


def test_concat_assistant_text_filters_non_assistant():
    data = [
        {"type": "system", "message": {"content": "ignore"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "text": "should-skip"},
                    {"type": "text", "text": "world"},
                ]
            },
        },
    ]
    assert _concat_assistant_text(data) == "hello\nworld"


def test_concat_assistant_text_handles_bad_shape():
    assert _concat_assistant_text(None) == ""
    assert _concat_assistant_text({"not": "a list"}) == ""
    assert _concat_assistant_text([{"type": "assistant"}]) == ""


@pytest.mark.parametrize(
    "text,stage,expected",
    [
        ("Council Score: 8.00/10", "s1", 8.0),
        ("Score: 7.50/10", "s1", 7.5),
        ("Plan Score: 6.2/10", "s2", 6.2),
        ("Score: 5/10\nLater Score: 9/10", "s2", 9.0),
        ("no score here", "s1", None),
    ],
)
def test_extract_score_regex(text, stage, expected):
    assert _extract_score_regex(text, stage) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Ship/Show/Ask: Ship", "ship"),
        ("Classification: show", "show"),
        ("no mode anywhere", "ask"),
        ("Ship/Show/Ask:ASK", "ask"),
    ],
)
def test_extract_mode(text, expected):
    assert _extract_mode(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Estimate: 5 pts", 5),
        ("(13 pts)", 13),
        ("this is 8 pts reasonable", 8),
        ("Total: ~250 LOC", 5),
        ("Estimated LOC: 80", 3),
        ("~400 LOC", 8),
        ("nothing numeric here", 0),
    ],
)
def test_extract_estimate_points(text, expected):
    assert _extract_estimate_points(text) == expected


def test_parse_s1_fixture_regex_path():
    data = json.loads((FIXTURES / "council_s1_execution.json").read_text())
    text = _concat_assistant_text(data)
    result = parse_text(text, "s1", source_hint="regex")
    assert result["score"] == 8.0
    assert result["verdict"] == "go"
    assert result["mode"] == "ship"
    assert result["estimate_points"] == 5
    assert result["source"] == "regex"


def test_parse_s2_fixture_uses_plan_score_first():
    data = json.loads((FIXTURES / "council_s2_execution.json").read_text())
    text = _concat_assistant_text(data)
    result = parse_text(text, "s2", source_hint="regex")
    assert result["score"] == 7.5
    assert result["verdict"] == "fix"
    assert result["mode"] == "show"
    assert result["source"] == "regex"


def test_parse_structured_json_overrides_regex():
    data = json.loads((FIXTURES / "council_structured_json.json").read_text())
    text = _concat_assistant_text(data)
    result = parse_text(text, "s1", source_hint="regex")
    assert result["source"] == "structured_json"
    assert result["score"] == 8.75
    assert result["verdict"] == "go"
    assert result["mode"] == "ship"
    assert result["estimate_points"] == 3


def test_run_oversize_execution_file_refuses_loudly(tmp_path, capsys):
    import os

    big = tmp_path / "huge.json"
    big.write_text("[]")
    os.truncate(big, 10 * 1024 * 1024 + 1)
    code, result = run(big, "s1", fallback_comment=None, strict=False)
    assert code == 2
    assert result["score"] is None
    err = capsys.readouterr().err
    assert "exceeds" in err
    assert "pathological" in err


def test_run_missing_exec_file_returns_error(tmp_path):
    missing = tmp_path / "nope.json"
    code, result = run(missing, "s1", fallback_comment=None, strict=False)
    assert code == 1
    assert result["score"] is None


def test_run_missing_exec_with_fallback_comment(tmp_path):
    missing = tmp_path / "nope.json"
    fallback = tmp_path / "comment.md"
    fallback.write_text("Summary.\n\nCouncil Score: 9.2/10 — Go\nShip/Show/Ask: Ship\n")
    code, result = run(missing, "s1", fallback_comment=fallback, strict=False)
    assert code == 0
    assert result["score"] == 9.2
    assert result["verdict"] == "go"
    assert result["source"] == "fallback"


def test_run_strict_raises_when_empty(tmp_path):
    exec_file = tmp_path / "empty.json"
    exec_file.write_text("[]")
    code, result = run(exec_file, "s1", fallback_comment=None, strict=True)
    assert code == 1
    assert result["score"] is None


def test_run_fallback_not_used_when_exec_has_score(tmp_path):
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Council Score: 8.1/10 — Go"}
                        ]
                    },
                }
            ]
        )
    )
    fallback = tmp_path / "comment.md"
    fallback.write_text("Council Score: 3.0/10 — Redo")
    code, result = run(exec_file, "s1", fallback_comment=fallback, strict=False)
    assert code == 0
    assert result["score"] == 8.1
    assert result["source"] == "regex"


def test_main_emits_single_line_json(capsys, tmp_path):
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Plan Score: 7.0/10 — Fix"}
                        ]
                    },
                }
            ]
        )
    )
    code = main(["--execution-file", str(exec_file), "--stage", "s2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "\n" not in out.rstrip("\n")
    parsed = json.loads(out)
    assert parsed["score"] == 7.0
    assert parsed["verdict"] == "fix"


def test_script_end_to_end(tmp_path):
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Council Score: 8.5/10 — Go"}
                        ]
                    },
                }
            ]
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--execution-file",
            str(exec_file),
            "--stage",
            "s1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["score"] == 8.5
    assert payload["verdict"] == "go"
