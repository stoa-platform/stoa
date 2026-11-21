"""Unit tests for show_demo.py --preview exact decision_id correlation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "preview_demo.py"

IDS = {
    "limits": "11111111-1111-4111-8111-111111111111",
    "allow50": "22222222-2222-4222-8222-222222222222",
    "deny80": "33333333-3333-4333-8333-333333333333",
    "deny_cust": "44444444-4444-4444-8444-444444444444",
    "revoke": "55555555-5555-4555-8555-555555555555",
    "deny_revoked": "66666666-6666-4666-8666-666666666666",
}


def make_fixture(tmp: Path, *, mismatch_deny80: bool = False, extra_exec_for_deny: bool = False, gap: bool = False):
    trace = {
        "first_refusal_epoch_ms": 1763670000123,
        "steps": [
            {"step": "bootstrap", "http_status": 200},
            {"step": "delegate", "http_status": 200},
            {"step": "child_limits", "http_status": 200},
            {"step": "child_refund_50", "http_status": 200, "decision_id": IDS["allow50"]},
            {
                "step": "child_refund_80",
                "http_status": 200,
                "decision_id": IDS["deny80"],
                "error_code": -32003,
                "error_message": "Tool call rejected by role policy",
                "evidence": {
                    "decision_id": IDS["deny80"],
                    "reason": "argument_constraint_denied",
                    "constraint": "amount_exceeds_cap",
                    "limit_eur": 50,
                },
            },
            {
                "step": "child_other_customer",
                "http_status": 200,
                "decision_id": IDS["deny_cust"],
                "error_code": -32003,
                "error_message": "Tool call rejected by role policy",
                "evidence": {
                    "decision_id": IDS["deny_cust"],
                    "reason": "argument_constraint_denied",
                    "constraint": "customer_outside_scope",
                },
            },
            {"step": "revoke", "http_status": 200},
            {
                "step": "child_revoked_retry",
                "http_status": 200,
                "decision_id": IDS["deny_revoked"],
                "error_code": -32003,
                "error_message": "Chain revoked",
                "evidence": {
                    "decision_id": IDS["deny_revoked"],
                    "reason": "chain_revoked",
                },
            },
        ],
    }
    trace_path = tmp / "trace.json"
    trace_path.write_text(json.dumps(trace), encoding="utf-8")

    journal_dir = tmp / "journal"
    journal_dir.mkdir()
    (journal_dir / "decisions.health.json").write_text(
        json.dumps({"status": "healthy", "gap_detected": gap}), encoding="utf-8"
    )
    deny80_journal_id = "99999999-9999-4999-8999-999999999999" if mismatch_deny80 else IDS["deny80"]
    rows = [
        {"kind": "decision", "route": "direct", "tool": "stoa_security", "rule": "local_inspection", "result": "allowed", "reason": "local_inspection", "decision_id": IDS["limits"]},
        {"kind": "decision", "route": "direct", "tool": "refunds_create", "rule": "admission_budget", "result": "allowed", "reason": "ok", "decision_id": IDS["allow50"], "request_id": "req-1"},
        {"kind": "execution", "route": "direct", "tool": "refunds_create", "rule": "execution", "result": "succeeded", "reason": "execution_succeeded", "decision_id": IDS["allow50"], "request_id": "req-1"},
        {"kind": "decision", "route": "direct", "tool": "refunds_create", "rule": "argument_constraint", "result": "denied", "reason": "argument_constraint_denied", "decision_id": deny80_journal_id},
        {"kind": "decision", "route": "direct", "tool": "refunds_create", "rule": "argument_constraint", "result": "denied", "reason": "argument_constraint_denied", "decision_id": IDS["deny_cust"]},
        {"kind": "revocation", "route": "revoke", "tool": None, "rule": "revocation", "result": "changed", "reason": "revoked", "decision_id": IDS["revoke"]},
        {"kind": "decision", "route": "direct", "tool": "refunds_create", "rule": "chain_state", "result": "denied", "reason": "chain_revoked", "decision_id": IDS["deny_revoked"]},
    ]
    if extra_exec_for_deny:
        rows.insert(4, {"kind": "execution", "route": "direct", "tool": "refunds_create", "rule": "execution", "result": "succeeded", "reason": "execution_succeeded", "decision_id": deny80_journal_id, "request_id": "req-bad"})
    (journal_dir / "decisions.ndjson").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return trace_path, journal_dir


class ShowDemoPreviewTests(unittest.TestCase):
    def test_preview_passes_with_exact_uuid_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            trace_path, journal_dir = make_fixture(Path(td))
            res = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--preview", str(trace_path), str(journal_dir), "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn(IDS["allow50"], res.stdout)
            self.assertIn(IDS["deny80"], res.stdout)
            self.assertIn("4/4 client decision_id == journal", res.stdout)
            self.assertIn("caller_auth_headers_seen=0", res.stdout)

    def test_preview_fails_on_decision_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            trace_path, journal_dir = make_fixture(Path(td), mismatch_deny80=True)
            res = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--preview", str(trace_path), str(journal_dir), "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(res.returncode, 0)

    def test_preview_fails_on_unexpected_execution_row(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            trace_path, journal_dir = make_fixture(Path(td), extra_exec_for_deny=True)
            res = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--preview", str(trace_path), str(journal_dir), "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(res.returncode, 0)

    def test_preview_fails_on_journal_gap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            trace_path, journal_dir = make_fixture(Path(td), gap=True)
            res = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--preview", str(trace_path), str(journal_dir), "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
