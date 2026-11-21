from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent_demo_client import (
    CALL_ARGUMENTS,
    FIRST_PROMPT,
    RETRY_PROMPT,
    DemoClientError,
    Receipt,
    parse_tool_result,
    run_claude,
    validate_api_key_file,
)

UUID_0 = "11111111-1111-1111-1111-111111111111"
UUID_1 = "22222222-2222-2222-2222-222222222222"
UUID_3 = "33333333-3333-3333-3333-333333333333"


class ParseToolResultTests(unittest.TestCase):
    def test_valid_receipts_all_indices(self) -> None:
        cases = [
            (
                0,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool call rejected by role policy\ndecision_id={UUID_0}\nreason=argument_constraint_denied\nconstraint=amount_exceeds_cap\nlimit_eur=50\n",
                        }
                    ],
                },
                Receipt(
                    UUID_0,
                    "argument_constraint_denied",
                    "amount_exceeds_cap",
                    50,
                    "Tool call rejected by role policy",
                ),
            ),
            (
                1,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool call rejected by role policy\ndecision_id={UUID_1}\nreason=argument_constraint_denied\nconstraint=customer_outside_scope",
                        }
                    ],
                },
                Receipt(
                    UUID_1,
                    "argument_constraint_denied",
                    "customer_outside_scope",
                    None,
                    "Tool call rejected by role policy",
                ),
            ),
            (
                2,
                {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({**CALL_ARGUMENTS[2], "status": "simulated"}),
                        }
                    ],
                },
                Receipt(None, "ok", None, None, "simulated"),
            ),
            (
                3,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Chain revoked\ndecision_id={UUID_3}\nreason=chain_revoked",
                        }
                    ],
                },
                Receipt(UUID_3, "chain_revoked", None, None, "Chain revoked"),
            ),
        ]
        for idx, payload, expected in cases:
            self.assertEqual(parse_tool_result(idx, payload), expected)

    def test_rejects_malformed_and_redacts_secret(self) -> None:
        secret = "sk-ant-SECRET-TOKEN-999"
        bad_cases = [
            (True, {"isError": True, "content": []}),
            (4, {"isError": False, "content": []}),
            (
                2,
                {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": '{"customer_id":"C-1042","amount_eur":50,"amount_eur":50,"currency":"EUR","status":"simulated"}',
                        }
                    ],
                },
            ),
            (
                2,
                {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": '{"customer_id":"C-1042","amount_eur":true,"currency":"EUR","status":"simulated"}',
                        }
                    ],
                },
            ),
            (
                0,
                {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": secret},
                        {"type": "text", "text": "extra"},
                    ],
                },
            ),
        ]
        for idx, payload in bad_cases:
            with self.assertRaises(DemoClientError) as ctx:
                parse_tool_result(idx, payload)
            self.assertNotIn(secret, str(ctx.exception))


class ApiKeyFileTests(unittest.TestCase):
    def test_key_file_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.key"
            with self.assertRaises(DemoClientError) as ctx:
                validate_api_key_file(missing)
            self.assertNotIn(str(missing), str(ctx.exception))

            key_path = root / "api.key"
            key_path.write_text("sk-ant-valid-key\n", encoding="ascii")
            os.chmod(key_path, 0o644)
            with self.assertRaises(DemoClientError):
                validate_api_key_file(key_path)

            os.chmod(key_path, 0o600)
            validate_api_key_file(key_path)

            link_path = root / "link.key"
            os.symlink(key_path, link_path)
            with self.assertRaises(DemoClientError):
                validate_api_key_file(link_path)


class RunClaudeStubTests(unittest.TestCase):
    def test_two_turns_same_process_and_env_isolation(self) -> None:
        py_bin = str(Path(sys.executable).resolve())
        stub_code = rf"""#!{py_bin}
import json, os, sys

assert "sk-ant-test-only" not in " ".join(sys.argv)
assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-only"
assert os.environ.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") == "1"
assert os.environ.get("PATH") == os.defpath
assert "HTTP_PROXY" not in os.environ

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

assert json.loads(sys.stdin.readline())["type"] == "user"
emit({{"type": "assistant", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_use", "id": "c0", "name": "mcp__refunds__refunds_create", "input": {{"customer_id": "C-1042", "amount_eur": 80, "currency": "EUR"}}}}]}}}})
emit({{"type": "user", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_result", "tool_use_id": "c0", "is_error": True, "content": "Tool call rejected by role policy\ndecision_id={UUID_0}\nreason=argument_constraint_denied\nconstraint=amount_exceeds_cap\nlimit_eur=50"}}]}}}})
emit({{"type": "assistant", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_use", "id": "c1", "name": "mcp__refunds__refunds_create", "input": {{"customer_id": "C-2000", "amount_eur": 50, "currency": "EUR"}}}}]}}}})
emit({{"type": "user", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_result", "tool_use_id": "c1", "is_error": True, "content": [{{"type": "text", "text": "Tool call rejected by role policy\ndecision_id={UUID_1}\nreason=argument_constraint_denied\nconstraint=customer_outside_scope"}}]}}]}}}})
emit({{"type": "assistant", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_use", "id": "c2", "name": "mcp__refunds__refunds_create", "input": {{"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR"}}}}]}}}})
emit({{"type": "user", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_result", "tool_use_id": "c2", "content": json.dumps({{"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR", "status": "simulated"}})}}]}}}})
emit({{"type": "result", "subtype": "success", "is_error": False}})

assert json.loads(sys.stdin.readline())["type"] == "user"
emit({{"type": "assistant", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_use", "id": "c3", "name": "mcp__refunds__refunds_create", "input": {{"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR"}}}}]}}}})
emit({{"type": "user", "parent_tool_use_id": None, "message": {{"content": [{{"type": "tool_result", "tool_use_id": "c3", "is_error": True, "content": "Chain revoked\ndecision_id={UUID_3}\nreason=chain_revoked"}}]}}}})
emit({{"type": "result", "subtype": "success", "is_error": False}})
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "fake_claude.py"
            stub.write_text(stub_code, encoding="utf-8")
            os.chmod(stub, 0o700)
            key_path = root / "api.key"
            key_path.write_text("sk-ant-test-only\n", encoding="ascii")
            os.chmod(key_path, 0o600)
            profile = root / "profile"
            profile.mkdir()
            mcp_cfg = root / "mcp.json"
            mcp_cfg.write_text("{}", encoding="utf-8")

            events: list[tuple[str, object]] = []
            run_claude(
                executable=str(stub),
                profile=profile,
                cwd=root,
                mcp_config=mcp_cfg,
                api_key_file=key_path,
                deadline=time.monotonic() + 5.0,
                on_prompt=lambda p: events.append(("prompt", p)),
                on_result=lambda i, r: events.append(("result", (i, r.reason))),
                revoke=lambda: events.append(("revoke", None)),
            )
            self.assertEqual(
                events,
                [
                    ("prompt", FIRST_PROMPT),
                    ("result", (0, "argument_constraint_denied")),
                    ("result", (1, "argument_constraint_denied")),
                    ("result", (2, "ok")),
                    ("revoke", None),
                    ("prompt", RETRY_PROMPT),
                    ("result", (3, "chain_revoked")),
                ],
            )


if __name__ == "__main__":
    unittest.main()
