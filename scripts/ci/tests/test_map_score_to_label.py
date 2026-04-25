"""Unit tests for scripts/ci/map_score_to_label.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from map_score_to_label import main, map_score

SCRIPT = Path(__file__).resolve().parent.parent / "map_score_to_label.py"


@pytest.mark.parametrize(
    "score,namespace,expected",
    [
        (10.0, "ticket", "council:ticket-go"),
        (8.0, "ticket", "council:ticket-go"),
        (7.99, "ticket", "council:ticket-fix"),
        (6.0, "ticket", "council:ticket-fix"),
        (5.99, "ticket", "council:ticket-redo"),
        (0.0, "ticket", "council:ticket-redo"),
        (8.5, "plan", "council:plan-go"),
        (8.0, "plan", "council:plan-go"),
        (6.5, "plan", "council:plan-fix"),
        (6.0, "plan", "council:plan-fix"),
        (4.0, "plan", "council:plan-redo"),
    ],
)
def test_map_score_thresholds(score, namespace, expected):
    assert map_score(score, namespace) == expected


def test_map_score_invalid_namespace():
    with pytest.raises(ValueError, match="namespace must be"):
        map_score(8.0, "unknown")


def test_main_prints_label(capsys):
    exit_code = main(["--score", "8.2", "--namespace", "ticket"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "council:ticket-go"


def test_main_invalid_score(capsys):
    exit_code = main(["--score", "not-a-number", "--namespace", "ticket"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "invalid score" in captured.err


def test_main_missing_args():
    with pytest.raises(SystemExit) as exc:
        main(["--score", "8.0"])
    assert exc.value.code == 2


def test_script_help_exits_cleanly():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Council score" in result.stdout


def test_script_end_to_end():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--score", "7.5", "--namespace", "plan"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "council:plan-fix"
