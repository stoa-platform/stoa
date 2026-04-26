"""Regression tests for CAB-2175.

When the Council prompt instructs Claude to post the report via `gh issue
comment`, the "Council Score" / "Plan Score" trailer lands inside a
`tool_use.input` block of the claude-code-action execution file, not in
any `assistant.content[].text` turn. `parse_council_report.py` reads only
assistant text, so without a comment-body fallback the parser returns
`score=null verdict=null` on every Stage 1/2 run.

The fix wires `council-run/action.yml` to fetch the latest matching
issue comment created at or after a pre-Claude baseline timestamp, write
it to `$RUNNER_TEMP/council-fallback.md`, and pass that path to the
parser via `--fallback-comment`.

These tests pin the parser end of the contract:

- ``test_s1_fallback_recovers_score`` — execution file with assistant
  text but no S1 trailer + fallback comment with the trailer →
  parser returns score=8.75, verdict=go, source=fallback.
- ``test_s2_fallback_recovers_score`` — same, S2 path with
  "Plan Score" marker.
- ``test_no_fallback_keeps_null_when_exec_lacks_trailer`` — when the
  composite's stale-comment filter returns no match (no fallback file
  passed), the parser must keep score=None / verdict=None rather than
  fabricate a value. This pins the fail-closed contract that lets the
  Phase 2d verdict gate suppress label/Linear writes on stale-only
  state.

Bash-side fetch logic (createdAt floor, marker selection) is exercised
end-to-end by the §H.2 smoke run after merge; not unit-tested here.
"""

from __future__ import annotations

import json

from parse_council_report import run


def test_s1_fallback_recovers_score(tmp_path):
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "I will post the Council report."}
                        ]
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Comment posted."}]
                    },
                },
            ]
        )
    )
    fallback = tmp_path / "comment.md"
    fallback.write_text(
        "## Council Validation — Stage 1 (Ticket Pertinence)\n\n"
        "**Persona Average**: 8.75/10\n\n"
        "**Council Score: 8.75/10 — Go**\n"
        "Comment `/go` to approve and start plan validation (Stage 2).\n"
    )
    code, result = run(exec_file, "s1", fallback_comment=fallback, strict=False)
    assert code == 0
    assert result["score"] == 8.75
    assert result["verdict"] == "go"
    assert result["mode"] == "ask"
    assert result["source"] == "fallback"


def test_s2_fallback_recovers_score(tmp_path):
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Posting Stage 2 plan validation."}
                        ]
                    },
                }
            ]
        )
    )
    fallback = tmp_path / "comment.md"
    fallback.write_text(
        "## Stage 2: Plan Validation\n\n"
        "Classification: Show\n"
        "Estimate: 5 pts\n\n"
        "**Plan Score: 7.20/10 — Fix**\n"
        "Comment `/go-plan` to start implementation.\n"
    )
    code, result = run(exec_file, "s2", fallback_comment=fallback, strict=False)
    assert code == 0
    assert result["score"] == 7.2
    assert result["verdict"] == "fix"
    assert result["mode"] == "show"
    assert result["estimate_points"] == 5
    assert result["source"] == "fallback"


def test_no_fallback_keeps_null_when_exec_lacks_trailer(tmp_path):
    # Simulates the composite's stale-comment guard rejecting all
    # candidates: the bash fetch step writes nothing, so the parse
    # step calls the parser without --fallback-comment. Parser must
    # keep score=None / verdict=None to let the Phase 2d verdict gate
    # close.
    exec_file = tmp_path / "exec.json"
    exec_file.write_text(
        json.dumps(
            [
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Comment posted; awaiting review."}
                        ]
                    },
                }
            ]
        )
    )
    code, result = run(exec_file, "s1", fallback_comment=None, strict=False)
    assert code == 0
    assert result["score"] is None
    assert result["verdict"] is None
    assert result["source"] == "regex"
