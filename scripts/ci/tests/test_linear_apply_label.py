"""Unit tests for scripts/ci/linear_apply_label.py."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

import linear_apply_label
from linear_apply_label import apply_label_and_comment, main

SCRIPT = Path(__file__).resolve().parent.parent / "linear_apply_label.py"


class FakeGraphQL:
    """Stub replacement for linear_apply_label._graphql.

    Accepts a list of (response_or_exception, expected_query_substring?)
    pairs and returns them in order. Records every call for assertion.
    """

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, query: str, variables: dict, api_key: str, *, timeout: int = 10):
        self.calls.append((query, variables))
        if not self.responses:
            raise AssertionError(f"unexpected extra _graphql call: {query!r}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def patch_graphql(monkeypatch):
    def _apply(responses):
        fake = FakeGraphQL(responses)
        monkeypatch.setattr(linear_apply_label, "_graphql", fake)
        return fake

    return _apply


def test_no_api_key_returns_skipped(patch_graphql):
    fake = patch_graphql([])
    result = apply_label_and_comment("CAB-1", "ticket", 8.5, "body", api_key=None)
    assert result["skipped_reason"] == "no_api_key"
    assert result["applied_label"] is None
    assert result["target_label"] == "council:ticket-go"
    assert fake.calls == []


def test_ticket_not_found(patch_graphql):
    patch_graphql([{"issueSearch": {"nodes": []}}])
    result = apply_label_and_comment("CAB-1", "ticket", 8.5, "body", api_key="xx")
    assert result["skipped_reason"] == "ticket_not_found"
    assert result["issue_id"] is None


def test_label_not_found_still_posts_comment(patch_graphql):
    fake = patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "issue-abc"}]}},
            {"issueLabels": {"nodes": []}},
            {"commentCreate": {"success": True}},
        ]
    )
    result = apply_label_and_comment("CAB-1", "ticket", 8.5, "body", api_key="xx")
    assert result["issue_id"] == "issue-abc"
    assert result["applied_label"] is None
    assert result["skipped_reason"] == "label_not_found"
    assert result["comment_posted"] is True
    assert len(fake.calls) == 3


def test_happy_path_dedups_existing_namespace(patch_graphql):
    fake = patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "issue-abc"}]}},
            {"issueLabels": {"nodes": [{"id": "label-go"}]}},
            {
                "issue": {
                    "labels": {
                        "nodes": [
                            {"id": "keep-1", "name": "priority:high"},
                            {"id": "drop-1", "name": "council:ticket-fix"},
                            {"id": "drop-2", "name": "council:ticket-redo"},
                            {"id": "keep-2", "name": "instance:backend"},
                        ]
                    }
                }
            },
            {"issueUpdate": {"success": True}},
            {"commentCreate": {"success": True}},
        ]
    )
    result = apply_label_and_comment("CAB-1", "ticket", 8.5, "hello", api_key="xx")
    assert result["applied_label"] == "council:ticket-go"
    assert result["issue_id"] == "issue-abc"
    assert result["comment_posted"] is True
    assert result["skipped_reason"] is None

    update_call = fake.calls[3]
    sent_ids = update_call[1]["ids"]
    assert sent_ids == ["keep-1", "keep-2", "label-go"]


def test_plan_namespace_dedups_only_plan_labels(patch_graphql):
    patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "iid"}]}},
            {"issueLabels": {"nodes": [{"id": "new-label"}]}},
            {
                "issue": {
                    "labels": {
                        "nodes": [
                            {"id": "t-keep", "name": "council:ticket-go"},
                            {"id": "p-drop", "name": "council:plan-fix"},
                        ]
                    }
                }
            },
            {"issueUpdate": {"success": True}},
        ]
    )
    result = apply_label_and_comment("CAB-1", "plan", 7.0, "", api_key="xx")
    assert result["applied_label"] == "council:plan-fix"
    assert result["comment_posted"] is False  # empty body


def test_network_error_propagates(patch_graphql):
    patch_graphql([urllib.error.URLError("timeout")])
    with pytest.raises(urllib.error.URLError):
        apply_label_and_comment("CAB-1", "ticket", 8.5, "body", api_key="xx")


def test_comment_create_failure_does_not_abort_label(patch_graphql, capsys):
    patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "iid"}]}},
            {"issueLabels": {"nodes": [{"id": "lid"}]}},
            {"issue": {"labels": {"nodes": []}}},
            {"issueUpdate": {"success": True}},
            ValueError("boom"),
        ]
    )
    result = apply_label_and_comment("CAB-1", "ticket", 8.5, "body", api_key="xx")
    assert result["applied_label"] == "council:ticket-go"
    assert result["comment_posted"] is False
    assert "commentCreate failed" in capsys.readouterr().err


def test_score_below_threshold_picks_redo(patch_graphql):
    patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "iid"}]}},
            {"issueLabels": {"nodes": [{"id": "lid"}]}},
            {"issue": {"labels": {"nodes": []}}},
            {"issueUpdate": {"success": True}},
        ]
    )
    result = apply_label_and_comment("CAB-1", "ticket", 4.2, "", api_key="xx")
    assert result["applied_label"] == "council:ticket-redo"


def test_main_emits_single_line_json(patch_graphql, capsys, monkeypatch):
    patch_graphql(
        [
            {"issueSearch": {"nodes": [{"id": "iid"}]}},
            {"issueLabels": {"nodes": [{"id": "lid"}]}},
            {"issue": {"labels": {"nodes": []}}},
            {"issueUpdate": {"success": True}},
            {"commentCreate": {"success": True}},
        ]
    )
    monkeypatch.setenv("LINEAR_API_KEY", "xx")
    code = main(
        [
            "--ticket-id",
            "CAB-1",
            "--namespace",
            "ticket",
            "--score",
            "8.8",
            "--comment-body",
            "hello",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "\n" not in out.rstrip("\n")
    parsed = json.loads(out)
    assert parsed["applied_label"] == "council:ticket-go"
    assert parsed["comment_posted"] is True


def test_main_no_api_key_still_exits_zero(patch_graphql, capsys, monkeypatch):
    patch_graphql([])
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    code = main(
        [
            "--ticket-id",
            "CAB-1",
            "--namespace",
            "ticket",
            "--score",
            "8.0",
        ]
    )
    assert code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["skipped_reason"] == "no_api_key"


def test_main_invalid_score_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("LINEAR_API_KEY", "xx")
    code = main(
        [
            "--ticket-id",
            "CAB-1",
            "--namespace",
            "ticket",
            "--score",
            "not-numeric",
        ]
    )
    assert code == 2
    assert "invalid score" in capsys.readouterr().err


def test_main_network_error_exits_1(patch_graphql, monkeypatch, capsys):
    patch_graphql([urllib.error.URLError("conn refused")])
    monkeypatch.setenv("LINEAR_API_KEY", "xx")
    code = main(
        [
            "--ticket-id",
            "CAB-1",
            "--namespace",
            "ticket",
            "--score",
            "8.0",
        ]
    )
    assert code == 1
    assert "Linear sync failed" in capsys.readouterr().err


def test_script_help_runs():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "namespace" in result.stdout.lower()
