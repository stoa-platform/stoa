"""Unit tests for scripts/ci/detect_pr_for_issue.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import detect_pr_for_issue
from detect_pr_for_issue import find_pr, main

SCRIPT = Path(__file__).resolve().parent.parent / "detect_pr_for_issue.py"


class FakeGh:
    def __init__(self, response: list[dict] | str | Exception):
        self.calls: list[list[str]] = []
        self.response = response

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response)


def _patch_gh(monkeypatch, response):
    fake = FakeGh(response)
    monkeypatch.setattr(detect_pr_for_issue, "_run_gh", fake)
    return fake


def test_find_pr_happy_path_via_ticket_id(monkeypatch):
    fake = _patch_gh(
        monkeypatch,
        [
            {
                "number": 1234,
                "url": "https://github.com/x/y/pull/1234",
                "state": "OPEN",
                "headRefName": "feat/cab-2166-ci-rewrite",
                "title": "refactor(ci): CAB-2166 extract scripts",
            }
        ],
    )
    result = find_pr(issue_number=42, ticket_id="CAB-2166")
    assert result == {
        "pr_found": True,
        "pr_num": 1234,
        "pr_url": "https://github.com/x/y/pull/1234",
        "pr_state": "OPEN",
    }
    assert fake.calls[0][:4] == ["pr", "list", "--state", "all"]
    assert "CAB-2166" in fake.calls[0]


def test_find_pr_happy_path_via_issue_ref(monkeypatch):
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 99,
                "url": "https://github.com/x/y/pull/99",
                "state": "MERGED",
                "headRefName": "feat/issue-42-feature",
                "title": "fix: thing for issue-42",
            }
        ],
    )
    result = find_pr(issue_number=42, ticket_id=None)
    assert result["pr_found"] is True
    assert result["pr_num"] == 99
    assert result["pr_state"] == "MERGED"


def test_find_pr_rejects_false_positive(monkeypatch, capsys):
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 500,
                "url": "https://github.com/x/y/pull/500",
                "state": "OPEN",
                "headRefName": "feat/unrelated",
                "title": "random work",
            }
        ],
    )
    result = find_pr(issue_number=42, ticket_id="CAB-2166")
    assert result == {"pr_found": False}
    err = capsys.readouterr().err
    assert "false positive" in err


def test_find_pr_matches_on_title_only(monkeypatch):
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 77,
                "url": "https://github.com/x/y/pull/77",
                "state": "OPEN",
                "headRefName": "some-random-branch",
                "title": "chore: address issue-42 cleanup",
            }
        ],
    )
    result = find_pr(issue_number=42, ticket_id=None)
    assert result["pr_found"] is True


def test_find_pr_no_prs(monkeypatch):
    _patch_gh(monkeypatch, [])
    assert find_pr(issue_number=42, ticket_id="CAB-1") == {"pr_found": False}


def test_find_pr_empty_stdout(monkeypatch):
    _patch_gh(monkeypatch, "")
    assert find_pr(issue_number=42, ticket_id=None) == {"pr_found": False}


def test_find_pr_case_insensitive_match(monkeypatch):
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 10,
                "url": "u",
                "state": "OPEN",
                "headRefName": "Feat/CAB-1234-thing",
                "title": "stuff",
            }
        ],
    )
    result = find_pr(issue_number=1, ticket_id="cab-1234")
    assert result["pr_found"] is True


def test_find_pr_gh_error(monkeypatch):
    err = subprocess.CalledProcessError(returncode=4, cmd=["gh"], stderr="auth failed")
    _patch_gh(monkeypatch, err)
    with pytest.raises(subprocess.CalledProcessError):
        find_pr(issue_number=1, ticket_id=None)


def test_main_writes_json(capsys, monkeypatch):
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 1,
                "url": "u",
                "state": "OPEN",
                "headRefName": "feat/CAB-1-x",
                "title": "title CAB-1",
            }
        ],
    )
    monkeypatch.setenv("GH_TOKEN", "xx")
    code = main(["--issue-number", "1", "--ticket-id", "CAB-1"])
    assert code == 0
    out = capsys.readouterr().out
    assert "\n" not in out.rstrip("\n")
    parsed = json.loads(out)
    assert parsed["pr_found"] is True


def test_main_gh_failure_exits_1(monkeypatch, capsys):
    err = subprocess.CalledProcessError(returncode=4, cmd=["gh"], stderr="boom")
    _patch_gh(monkeypatch, err)
    monkeypatch.setenv("GH_TOKEN", "xx")
    code = main(["--issue-number", "1"])
    assert code == 1
    assert "boom" in capsys.readouterr().err


def test_main_warns_without_token(monkeypatch, capsys):
    _patch_gh(monkeypatch, [])
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    code = main(["--issue-number", "1"])
    assert code == 0
    assert "neither GH_TOKEN" in capsys.readouterr().err


def test_script_help_runs():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "issue number" in result.stdout.lower()
