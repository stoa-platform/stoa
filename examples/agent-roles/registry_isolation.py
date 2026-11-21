#!/usr/bin/env python3
"""Local Control Plane fixture and mixed-profile MCP Compose checks."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import Lock
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen


CONTROL_PLANE = "http://control-plane-mock:8000"
FIXTURE_LOOPBACK = "http://127.0.0.1:8000"
ISSUER = f"{CONTROL_PLANE}/realms/stoa"
ISSUER_PATH = "/realms/stoa"
OIDC_PATH = f"{ISSUER_PATH}/protocol/openid-connect"
AUDIENCE = "registry-fixture-mcp"
IDENTITY = "registry-standard-fixture"
KEY_ID = "registry-fixture-key"
STARTUP_TOOL = "payments_list"
REFRESHED_TOOL = "payments_outbound_blocked"
STARTUP_DESCRIPTION = "Control Plane startup definition"
REFRESHED_DESCRIPTION = "Control Plane refreshed definition"
GUARD_PATH = "/registry-guard-target"
COUNTERS = {
    "remote_discoveries": 0,
    "tenant_discoveries": 0,
    "startup_tool_calls": 0,
    "refreshed_tool_calls": 0,
    "guard_target_calls": 0,
    "caller_auth_headers_seen": 0,
}
COUNTERS_LOCK = Lock()


def encoded(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unsigned_integer(value: int) -> str:
    return encoded(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def issue_token(key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": IDENTITY,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 180,
        "tenant_id": "acme",
        "scope": "stoa:read",
        "realm_access": {"roles": ["viewer"]},
    }
    header = {"alg": "RS256", "kid": KEY_ID, "typ": "JWT"}
    message = ".".join(encoded(json.dumps(part).encode()) for part in (header, claims))
    signature = key.sign(message.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{message}.{encoded(signature)}"


def serve() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()
    jwks = {
        "keys": [{
            "kty": "RSA",
            "kid": KEY_ID,
            "alg": "RS256",
            "use": "sig",
            "n": unsigned_integer(public.n),
            "e": unsigned_integer(public.e),
        }],
    }
    discovery = {
        "issuer": ISSUER,
        "authorization_endpoint": f"{CONTROL_PLANE}{OIDC_PATH}/auth",
        "token_endpoint": f"{CONTROL_PLANE}{OIDC_PATH}/token",
        "jwks_uri": f"{CONTROL_PLANE}{OIDC_PATH}/certs",
    }

    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def reply(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def count(self, key: str) -> None:
            with COUNTERS_LOCK:
                COUNTERS[key] += 1
                if "Authorization" in self.headers:
                    COUNTERS["caller_auth_headers_seen"] += 1

        def do_GET(self) -> None:
            target = urlsplit(self.path)
            path = target.path
            if path == "/health":
                self.reply({"status": "ok"})
            elif path == f"{ISSUER_PATH}/.well-known/openid-configuration":
                self.reply(discovery)
            elif path == f"{OIDC_PATH}/certs":
                self.reply(jwks)
            elif path == "/v1/mcp/tools":
                self.count("remote_discoveries")
                self.reply({"tools": [{
                    "name": STARTUP_TOOL,
                    "description": STARTUP_DESCRIPTION,
                    "inputSchema": {"type": "object", "properties": {"source": {"type": "string"}}},
                }]})
            elif path == "/v1/mcp/generated-tools" and parse_qs(target.query) == {"tenant_id": ["acme"]}:
                self.count("tenant_discoveries")
                self.reply({"tenant_id": "acme", "total": 1, "tools": [{
                    "tool_name": REFRESHED_TOOL,
                    "description": REFRESHED_DESCRIPTION,
                    "input_schema": {"type": "object", "properties": {}},
                    "http_method": "GET",
                    "version": "1",
                    "enabled": True,
                }]})
            elif path in ("/v1/internal/catalog/apis", "/v1/internal/catalog/apis/expanded"):
                self.reply({"apis": [], "tools": []})
            elif path == GUARD_PATH:
                self.count("guard_target_calls")
                self.reply({"source": "guard-target"})
            elif self.client_address[0] == "127.0.0.1" and path == "/fixture/token":
                self.reply({"access_token": issue_token(key)})
            elif self.client_address[0] == "127.0.0.1" and path == "/fixture/stats":
                with COUNTERS_LOCK:
                    snapshot = dict(COUNTERS)
                self.reply(snapshot)
            else:
                self.reply({"status": "not_found"}, 404)

        def do_POST(self) -> None:
            if self.path == f"/v1/mcp/tools/{STARTUP_TOOL}/invoke":
                counter, marker = "startup_tool_calls", "cp-startup"
            elif self.path == f"/v1/mcp/tools/{REFRESHED_TOOL}/invoke":
                counter, marker = "refreshed_tool_calls", "cp-refresh"
            else:
                self.reply({"status": "not_found"}, 404)
                return
            self.count(counter)
            self.reply({"isError": False, "content": [{"type": "text", "text": marker}]})

    with ThreadingHTTPServer(("0.0.0.0", 8000), FixtureHandler) as server:
        server.serve_forever()


def prepare_fixtures(directory: Path) -> None:
    contract_path = directory / "contracts" / "payments.uac.json"
    contract = json.loads(contract_path.read_text())
    endpoints = [
        endpoint
        for endpoint in contract["endpoints"]
        if endpoint["llm"]["tool_name"] == REFRESHED_TOOL
    ]
    assert len(endpoints) == 1, "expected one UAC endpoint for the outgoing check"
    endpoints[0]["backend_url"] = f"{CONTROL_PLANE}{GUARD_PATH}"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")

    # The global startup definition has no owning tenant, unlike UAC tools.
    with (directory / "opa" / "policy.rego").open("a") as policy:
        policy.write(f"""
allow if {{
    input.user_id == "{IDENTITY}"
    input.tenant_id == "acme"
    input.resource_tenant_id == null
    input.tool_name == "{STARTUP_TOOL}"
    input.action == "Read"
}}
""")


def prove() -> None:
    from agent_harness import DpopKey, http_req
    from jalon4 import bootstrap, call, rpc, spend

    gateway = os.environ["STOA_GATEWAY_URL"]
    bearer = sys.stdin.readline().strip()
    assert bearer, "fixture caller token was not available"
    standard_headers = {"Authorization": f"Bearer {bearer}"}
    key = DpopKey()
    token = bootstrap(gateway, key, "registry-poc-fixture")["access_token"]
    poc_url = f"{gateway}/mcp/poc"

    def invoke_standard(name: str, args: dict, marker: str) -> None:
        status, payload = http_req(
            "POST", f"{gateway}/mcp/v1/tools/invoke", standard_headers,
            {"tool": name, "arguments": args},
        )
        assert status == 200, f"standard {name} returned HTTP {status}"
        result = json.loads(payload)
        assert result.get("isError") in (False, None) and result.get("content") == [
            {"type": "text", "text": marker},
        ], f"standard {name} did not reach its Control Plane target"

    def poc_definitions() -> dict:
        status, _, listing = rpc(poc_url, key, token, "tools/list", {})
        assert status == 200 and "result" in listing, f"PoC tool list returned HTTP {status}"
        return {tool["name"]: tool for tool in listing["result"]["tools"]}

    invoke_standard(STARTUP_TOOL, {"source": "startup"}, "cp-startup")
    spend(poc_url, key, token)
    before = poc_definitions()
    assert {STARTUP_TOOL, REFRESHED_TOOL} <= before.keys(), "PoC UAC definitions were missing"
    print("PASS: startup tool name resolves to the Control Plane and to local UAC on their respective surfaces")

    # Listing the tenant starts the real background Control Plane refresh.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status, payload = http_req("GET", f"{gateway}/mcp/v1/tools", standard_headers)
        assert status == 200, f"standard tool list returned HTTP {status}"
        standard = {tool["name"]: tool for tool in json.loads(payload)}
        if REFRESHED_TOOL in standard:
            break
        time.sleep(0.2)
    else:
        raise AssertionError("standard tenant catalog did not receive the refreshed tool")

    assert standard[REFRESHED_TOOL]["description"] == REFRESHED_DESCRIPTION, "standard refresh did not install the Control Plane definition"
    assert "source" in standard[STARTUP_TOOL]["inputSchema"]["properties"], "standard startup schema was not retained"
    assert poc_definitions() == before, "Control Plane refresh changed the PoC tool definitions"
    invoke_standard(STARTUP_TOOL, {"source": "refresh"}, "cp-startup")
    invoke_standard(REFRESHED_TOOL, {}, "cp-refresh")
    spend(poc_url, key, token)
    print("PASS: Control Plane refresh installs its own definition and preserves the signed-skill PoC catalog and backend")

    status, _, response = call(poc_url, key, token, REFRESHED_TOOL, {})
    assert status == 200 and response.get("error") == {
        "code": -32000, "message": "Tool execution failed",
    }, f"PoC outgoing check did not produce its execution refusal (HTTP {status})"
    print("PASS: the standard refreshed tool succeeds and its PoC counterpart still enforces the outgoing policy")


def check_counters() -> None:
    control_plane = json.loads(sys.stdin.readline())
    upstream = json.load(sys.stdin)
    totals = {
        "startup_tool_calls": 2,
        "refreshed_tool_calls": 1,
        "guard_target_calls": 0,
        "caller_auth_headers_seen": 0,
    }
    assert all(control_plane.get(key) == count for key, count in totals.items()), "unexpected Control Plane call counts"
    assert control_plane.get("remote_discoveries", 0) >= 2, "expected Control Plane discovery at startup and refresh"
    assert control_plane.get("tenant_discoveries", 0) >= 1, "expected Control Plane discovery for the tenant"
    assert upstream == {
        "upstream_calls": 2,
        "valid_api_key_calls": 2,
        "accepted_skill_context_calls": 2,
        "fail_calls": 0,
        "forbidden_calls": 0,
        "caller_auth_headers_seen": 0,
        "redirect_target_calls": 0,
        "oauth2_calls": 0,
    }, "unexpected upstream call counts"
    print(f"Control Plane mock: {json.dumps(control_plane, sort_keys=True)}")
    print(f"UAC upstream mock: {json.dumps(upstream, sort_keys=True)}")
    print("PASS: mocks received only their expected calls, with zero caller authorization headers and zero blocked target calls")


def fixture_payload(route: str) -> dict:
    with urlopen(f"{FIXTURE_LOOPBACK}/fixture/{route}", timeout=5) as response:
        return json.load(response)


if __name__ == "__main__":
    mode = sys.argv[1]
    try:
        if mode == "serve":
            serve()
        elif mode == "token":
            print(fixture_payload(mode)["access_token"])
        elif mode == "stats":
            print(json.dumps(fixture_payload(mode)))
        elif mode == "fixtures":
            prepare_fixtures(Path(sys.argv[2]))
        elif mode == "prove":
            prove()
        elif mode == "counters":
            check_counters()
        else:
            raise AssertionError("unknown registry fixture mode")
    except AssertionError as error:
        sys.exit(f"FAIL: {error}")
    except Exception as error:
        # Status and exception type are enough for diagnosis without response content.
        sys.exit(f"FAIL: registry fixture {mode} could not complete ({type(error).__name__})")
