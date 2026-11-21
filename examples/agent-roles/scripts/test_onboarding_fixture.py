#!/usr/bin/env python3
"""Local stdlib unit tests for onboarding_fixture.py and gen_fixtures.py --onboarding-demo."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import onboarding_fixture as fixture  # noqa: E402


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> tuple[int, dict[str, str], dict | None]:
    req_headers = dict(headers or {})
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, method=method, headers=req_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else None
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, parsed
    except urllib.error.HTTPError as err:
        with err:
            raw = err.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else None
            return err.code, {k.lower(): v for k, v in err.headers.items()}, parsed


class McpFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._marker = secrets.token_urlsafe(18)
        self.server, self.state = fixture.create_mcp_server(
            "127.0.0.1", 0, self._marker, max_sessions=2
        )
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._marker}"}

    def test_mcp_happy_path_and_safe_stats(self) -> None:
        code, headers, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers=self._auth(),
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
        )
        self.assertEqual(code, 200)
        session_id = headers.get("mcp-session-id")
        self.assertTrue(session_id)
        self.assertEqual(headers.get("mcp-protocol-version"), "2025-03-26")
        self.assertEqual(body["result"]["protocolVersion"], "2025-03-26")

        session_headers = {
            **self._auth(),
            "Mcp-Session-Id": session_id,
            "MCP-Protocol-Version": "2025-03-26",
        }
        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers=session_headers,
            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        self.assertEqual(code, 202)
        self.assertIsNone(body)

        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers=session_headers,
            body={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        self.assertEqual(code, 200)
        tools = body["result"]["tools"]
        self.assertEqual(len(tools), 1)
        tool = tools[0]
        self.assertEqual(tool["name"], "account_lookup")
        self.assertEqual(set(tool["inputSchema"].keys()), {"type", "properties", "required"})
        self.assertEqual(tool["inputSchema"]["type"], "object")
        self.assertEqual(tool["inputSchema"]["properties"], {"customer_id": {"type": "string"}})
        self.assertEqual(tool["inputSchema"]["required"], ["customer_id"])
        self.assertNotIn("additionalProperties", tool["inputSchema"])
        self.assertIs(tool["annotations"]["readOnlyHint"], True)

        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers=session_headers,
            body={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "account_lookup",
                    "arguments": {"customer_id": "C-1042", "unused_extra": "ignored"},
                },
            },
        )
        self.assertEqual(code, 200)
        content = body["result"]["content"]
        self.assertEqual(content[0]["type"], "text")
        decoded = json.loads(content[0]["text"])
        self.assertEqual(decoded["customer_id"], "C-1042")
        self.assertEqual(decoded["tier"], "synthetic")

        code, _, stats = http_json("GET", f"{self.base_url}/stats")
        self.assertEqual(code, 200)
        self.assertEqual(stats["initialize_ok"], 1)
        self.assertEqual(stats["notifications_initialized_ok"], 1)
        self.assertEqual(stats["tools_list_ok"], 1)
        self.assertEqual(stats["tools_call_ok"], 1)
        self.assertEqual(stats["forwarded_auth_caller"], 0)
        self.assertEqual(stats["input_denied"], 0)
        self.assertNotIn(self._marker, json.dumps(stats))
        self.assertNotIn(session_id, json.dumps(stats))

    def test_mcp_rejects_bad_auth_dpop_headers_and_args(self) -> None:
        # Missing auth
        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            body={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        self.assertEqual(code, 401)
        self.assertEqual(body, {"error": "unauthorized"})

        # Forwarded caller DPoP header must be rejected and counted
        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers={**self._auth(), "DPoP": "synthetic-proof"},
            body={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        self.assertEqual(code, 401)
        self.assertEqual(body, {"error": "unauthorized"})

        # Valid initialize then bad protocol header / bad tool args / bounded sessions
        code, headers, _ = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers=self._auth(),
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
        )
        self.assertEqual(code, 200)
        sid1 = headers["mcp-session-id"]

        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers={
                **self._auth(),
                "Mcp-Session-Id": sid1,
                "MCP-Protocol-Version": "2024-11-05",
            },
            body={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        self.assertEqual(code, 400)
        self.assertEqual(body, {"error": "unsupported_protocol_version"})

        code, _, body = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers={**self._auth(), "Mcp-Session-Id": sid1},
            body={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "account_lookup", "arguments": {"customer_id": ""}},
            },
        )
        self.assertEqual(code, 200)
        self.assertIn("error", body)

        # Bounded session eviction (max_sessions=2)
        for idx in (10, 11):
            c, _, _ = http_json(
                "POST",
                f"{self.base_url}/mcp",
                headers=self._auth(),
                body={"jsonrpc": "2.0", "id": idx, "method": "initialize", "params": {}},
            )
            self.assertEqual(c, 200)
        code, _, _ = http_json(
            "POST",
            f"{self.base_url}/mcp",
            headers={**self._auth(), "Mcp-Session-Id": sid1},
            body={"jsonrpc": "2.0", "id": 12, "method": "tools/list", "params": {}},
        )
        self.assertEqual(code, 404)

        _, _, stats = http_json("GET", f"{self.base_url}/stats")
        self.assertEqual(stats["forwarded_auth_caller"], 1)
        self.assertEqual(stats["auth_denied"], 2)
        self.assertGreaterEqual(stats["input_denied"], 3)
        self.assertEqual(stats["active_sessions"], 2)


class VaultFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._op_token = secrets.token_urlsafe(18)
        self._gw_token = secrets.token_urlsafe(18)
        self.server, self.state = fixture.create_vault_server(
            "127.0.0.1", 0, self._op_token, self._gw_token
        )
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_vault_cas0_readback_actor_separation_and_soft_delete(self) -> None:
        secret_id = str(uuid.uuid4())
        data_url = f"{self.base_url}/v1/secret/data/stoa/mcp/acme/fixture-local/{secret_id}/legacy"
        delete_url = f"{self.base_url}/v1/secret/delete/stoa/mcp/acme/fixture-local/{secret_id}/legacy"
        op_hdr = {"X-Vault-Token": self._op_token}
        gw_hdr = {"X-Vault-Token": self._gw_token}
        secret_data = {
            "allowed_origin": "http://127.0.0.1:9000",
            "headers": {"Authorization": "Bearer synthetic-runtime-value"},
        }
        payload = {"options": {"cas": 0}, "data": secret_data}

        # Gateway cannot write
        code, _, _ = http_json("POST", data_url, headers=gw_hdr, body=payload)
        self.assertEqual(code, 403)

        # Flat map data must be rejected strictly
        flat_payload = {"options": {"cas": 0}, "data": {"bearer": "synthetic-runtime-value"}}
        code, _, _ = http_json("POST", data_url, headers=op_hdr, body=flat_payload)
        self.assertEqual(code, 400)

        # Operator creates with cas=0 and structured {allowed_origin, headers} -> version 1
        code, _, body = http_json("POST", data_url, headers=op_hdr, body=payload)
        self.assertEqual(code, 200)
        self.assertEqual(body["data"]["version"], 1)

        # Second cas=0 write conflicts
        code, _, _ = http_json("POST", data_url, headers=op_hdr, body=payload)
        self.assertEqual(code, 400)

        # Both operator and gateway can read ?version=1 with exact data shape and metadata.version
        for hdr in (op_hdr, gw_hdr):
            code, _, body = http_json("GET", f"{data_url}?version=1", headers=hdr)
            self.assertEqual(code, 200)
            self.assertEqual(body["data"]["metadata"]["version"], 1)
            self.assertEqual(body["data"]["data"], secret_data)

        # Gateway cannot delete
        code, _, _ = http_json("POST", delete_url, headers=gw_hdr, body={"versions": [1]})
        self.assertEqual(code, 403)

        # Operator soft-deletes versions:[1] only
        code, _, _ = http_json("POST", delete_url, headers=op_hdr, body={"versions": [1, 2]})
        self.assertEqual(code, 400)

        code, _, body = http_json("POST", delete_url, headers=op_hdr, body={"versions": [1]})
        self.assertEqual(code, 204)
        self.assertIsNone(body)

        # Readback after soft-delete returns 404 with deletion_time
        code, _, body = http_json("GET", f"{data_url}?version=1", headers=gw_hdr)
        self.assertEqual(code, 404)
        self.assertTrue(body["data"]["metadata"]["deletion_time"])

        # Unknown tenant path rejected
        bad_url = f"{self.base_url}/v1/secret/data/stoa/mcp/other/fixture-local/{secret_id}/legacy"
        code, _, _ = http_json("GET", bad_url, headers=op_hdr)
        self.assertEqual(code, 403)

        # Safe stats check (never exposes tokens or secret payload)
        code, _, stats = http_json("GET", f"{self.base_url}/stats")
        self.assertEqual(code, 200)
        self.assertEqual(stats["cas_writes_ok"], 1)
        self.assertEqual(stats["cas_conflicts"], 1)
        self.assertEqual(stats["readbacks_by_actor"], {"operator": 1, "gateway": 1})
        self.assertEqual(stats["soft_deletes_ok"], 1)
        self.assertEqual(stats["role_violations"], 2)
        self.assertEqual(stats["path_violations"], 1)
        self.assertEqual(stats["active_secrets"], 0)
        self.assertEqual(stats["deleted_secrets"], 1)
        serialized = json.dumps(stats)
        self.assertNotIn(self._op_token, serialized)
        self.assertNotIn(self._gw_token, serialized)
        self.assertNotIn("synthetic-runtime-value", serialized)


class OnboardingFixturesGenerationTest(unittest.TestCase):
    def test_gen_fixtures_onboarding_demo(self) -> None:
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography not installed in this Python environment")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "runtime"
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "gen_fixtures.py"), str(out_dir), "--onboarding-demo"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

            def decode_jws_payload(path: Path) -> dict:
                token = path.read_text(encoding="utf-8").strip()
                payload_b64 = token.split(".")[1]
                payload_b64 += "=" * (-len(payload_b64) % 4)
                return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))

            role_payload = decode_jws_payload(out_dir / "roles" / "acme.roles.jws")
            self.assertEqual(role_payload["tenant_id"], "acme")
            self.assertEqual(
                list(role_payload["roles"].keys()),
                ["onboarding_operator"],
            )
            self.assertEqual(
                role_payload["roles"]["onboarding_operator"]["allowed_tools"],
                ["legacy__account_lookup"],
            )

            tool_payload = decode_jws_payload(out_dir / "policies" / "acme.jws")
            self.assertEqual(
                {(p["tool"], p["allowed"]) for p in tool_payload["permissions"]},
                {("legacy__account_lookup", True), ("stoa_security", True)},
            )

            limits = json.loads((out_dir / "contracts" / "my-limits.uac.json").read_text(encoding="utf-8"))
            self.assertEqual(limits["endpoints"][0]["llm"]["tool_name"], "stoa_security")
            self.assertEqual(
                limits["endpoints"][0]["llm"]["examples"][0]["expected_output_contains"]["role"]["name"],
                "onboarding_operator",
            )
            self.assertEqual(
                json.loads((out_dir / "credentials.json").read_text(encoding="utf-8")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
