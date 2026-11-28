#!/usr/bin/env python3
"""In-container verification helpers for the two PoC agents."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def int_to_b64url(n: int, length: int | None = None) -> str:
    byte_len = length if length is not None else max(1, (n.bit_length() + 7) // 8)
    return b64url(n.to_bytes(byte_len, "big"))


class DpopKey:
    def __init__(self, key: ec.EllipticCurvePrivateKey | None = None) -> None:
        self._key = key or ec.generate_private_key(ec.SECP256R1())
        pub = self._key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": int_to_b64url(pub.x, 32),
            "y": int_to_b64url(pub.y, 32),
        }

    def sign_proof(
        self, htm: str, htu: str, access_token: str | None = None, jti: str | None = None
    ) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.jwk}
        claims: dict = {
            "jti": jti or str(uuid.uuid4()),
            "htm": htm,
            "htu": htu,
            "iat": int(time.time()),
        }
        if access_token is not None:
            claims["ath"] = b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        signing_input = (
            f"{b64url(json.dumps(header, separators=(',', ':')).encode())}."
            f"{b64url(json.dumps(claims, separators=(',', ':')).encode())}"
        )
        der_sig = self._key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{signing_input}.{b64url(raw_sig)}"


def http_req(
    method: str, url: str, headers: dict[str, str] | None = None, body: dict | None = None
) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = dict(headers or {})
    if data is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def assert_tcp_unreachable(host: str, port: int, label: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2):
            raise AssertionError(f"FAIL: {label} ({host}:{port}) should NOT be reachable")
    except OSError:
        print(f"PASS: {label} ({host}:{port}) is unreachable", flush=True)


def make_hs256_token(kid: str, aud: str) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    payload = {
        "iss": "stoa-poc-local",
        "sub": "forged",
        "aud": aud,
        "tenant_id": "acme",
        "role": "reader",
        "chain_id": "c1",
        "jti": "j1",
        "depth": 0,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": "fake"},
    }
    inp = (
        f"{b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = hmac.new(b"not-rsa", inp.encode("ascii"), hashlib.sha256).digest()
    return f"{inp}.{b64url(sig)}"


def make_external_rs256_token(kid: str | None, aud: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    header: dict = {"alg": "RS256", "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid
    payload = {
        "iss": "stoa-poc-local",
        "sub": "forged-oidc",
        "aud": aud,
        "tenant_id": "acme",
        "role": "reader",
        "chain_id": "c1",
        "jti": "j1",
        "depth": 0,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": "fake"},
    }
    inp = (
        f"{b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = key.sign(inp.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{inp}.{b64url(sig)}"


def assert_rpc_error(
    status: int, body: str, code: int, message: str, *, http_status: int = 200
) -> None:
    error = json.loads(body).get("error", {})
    assert (status, error.get("code"), error.get("message")) == (http_status, code, message), (
        f"expected HTTP {http_status}, RPC {code} {message!r}; got HTTP {status}, RPC {error}"
    )


def assert_role_denial(status: int, body: str) -> None:
    assert_rpc_error(status, body, -32003, "Tool call rejected by role policy")


def call_poc_tool(
    gateway: str, dpop: DpopKey, token: str, name: str, arguments: dict
) -> tuple[int, str]:
    url = f"{gateway}/mcp/poc"
    return http_req(
        "POST",
        url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", url, access_token=token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def read_my_limits(gateway: str, dpop: DpopKey, token: str) -> dict:
    status, body = call_poc_tool(gateway, dpop, token, "stoa_security", {"action": "get_my_limits"})
    rpc = json.loads(body)
    assert status == 200 and "error" not in rpc, f"get_my_limits failed: HTTP {status}"
    result = rpc["result"]
    assert result["isError"] is False
    limits = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == limits
    return limits


def bootstrap_parent(gateway_url: str, dpop: DpopKey) -> dict:
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]
    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    code, body = http_req(
        "POST",
        boot_url,
        headers={
            "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
            "DPoP": dpop.sign_proof("POST", boot_url),
        },
        body={"sub": "agent-parent", "tenant_id": "acme", "role": "reader", "ttl_secs": 300},
    )
    assert code == 200, f"bootstrap failed: {code}"
    return json.loads(body)


def run_parent(
    gateway_url: str, upstream_ip: str, child_jwk: dict | None, dpop: DpopKey
) -> tuple[str, str | None]:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-parent -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-parent -> upstream-mock (IP)")

    code, body = http_req("GET", f"{gateway_url}/ready")
    assert code == 200 and body.strip() == "READY", f"/ready failed: {code} {body}"
    print("PASS: /ready returned 200 READY with local signed policy loaded", flush=True)

    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"/admin/health expected 404, got {code}"
    print("PASS: /admin/health returned 404 (isolated from agent containers)", flush=True)

    boot = bootstrap_parent(gateway_url, dpop)
    token = boot["access_token"]
    kid = boot["kid"]
    assert boot["token_type"] == "DPoP" and boot["depth"] == 0
    print(f"PASS: agent-parent bootstrapped RS256 DPoP token (kid={kid})", flush=True)

    mcp_url = f"{gateway_url}/mcp/poc"
    valid_args = {"currency": "USD", "account": "acct-parent-1", "limit": 80}
    call_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "payments_list", "arguments": valid_args},
    }
    first_proof = dpop.sign_proof("POST", mcp_url, access_token=token)
    code, body = http_req(
        "POST",
        mcp_url,
        headers={"Authorization": f"DPoP {token}", "DPoP": first_proof},
        body=call_body,
    )
    assert code == 200, f"MCP tools/call failed: {code} {body}"
    rpc = json.loads(body)
    assert "error" not in rpc, f"unexpected JSON-RPC error: {rpc}"
    assert "pay_001" in body
    print("PASS: agent-parent MCP tools/call with DPoP + conforming args succeeded", flush=True)

    # Negative auth checks
    negatives = [
        ("replayed DPoP proof", {"Authorization": f"DPoP {token}", "DPoP": first_proof}),
        (
            "Bearer scheme instead of DPoP",
            {
                "Authorization": f"Bearer {token}",
                "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
            },
        ),
        ("missing DPoP header", {"Authorization": f"DPoP {token}"}),
        (
            "HS256 token rejected",
            {
                "Authorization": f"DPoP {make_hs256_token(kid, mcp_url)}",
                "DPoP": dpop.sign_proof("POST", mcp_url),
            },
        ),
        (
            "missing kid rejected",
            {
                "Authorization": f"DPoP {make_external_rs256_token(None, mcp_url)}",
                "DPoP": dpop.sign_proof("POST", mcp_url),
            },
        ),
        (
            "external OIDC-like RSA key rejected",
            {
                "Authorization": f"DPoP {make_external_rs256_token(kid, mcp_url)}",
                "DPoP": dpop.sign_proof("POST", mcp_url),
            },
        ),
    ]
    for label, hdrs in negatives:
        c, _ = http_req("POST", mcp_url, headers=hdrs, body=call_body)
        assert c == 401, f"FAIL: {label} expected 401, got {c}"
        print(f"PASS: {label} -> 401", flush=True)

    child_tok = None
    if child_jwk is not None:
        # Jalon 2 parent checks: tools/list matches tools/call decisions (OPA-denied tool hidden)
        c, b = http_req(
            "POST",
            mcp_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
            },
            body={"jsonrpc": "2.0", "id": 19, "method": "tools/list", "params": {}},
        )
        assert c == 200, f"tools/list failed: {c} {b}"
        listed_names = [t["name"] for t in json.loads(b)["result"]["tools"]]
        assert "payments_list" in listed_names, f"expected payments_list in tools/list: {listed_names}"
        assert "payments_opa_denied" not in listed_names, (
            f"OPA-denied tool payments_opa_denied should be absent from tools/list: {listed_names}"
        )
        print("PASS: tools/list excludes OPA-denied tool (payments_opa_denied)", flush=True)

        # Jalon 2 parent checks: OPA negative, outbound address policy block, 3xx non-follow + scrubbed error
        for label, tool_name, rpc_code, rpc_message in [
            ("OPA negative case (payments_opa_denied)", "payments_opa_denied", -32003, "Tool call rejected by policy"),
            ("Outbound address policy blocks link-local IP", "payments_outbound_blocked", -32000, "Tool execution failed"),
        ]:
            c, b = http_req(
                "POST",
                mcp_url,
                headers={
                    "Authorization": f"DPoP {token}",
                    "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
                },
                body={
                    "jsonrpc": "2.0",
                    "id": 20,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": {}},
                },
            )
            assert_rpc_error(c, b, rpc_code, rpc_message)
            print(f"PASS: {label} denied (zero upstream calls)", flush=True)

        c, b = http_req(
            "POST",
            mcp_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
            },
            body={
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "payments_redirect", "arguments": {}},
            },
        )
        assert c == 200 and "error" in json.loads(b) and "sensitive-upstream-redirect-body" not in b
        print("PASS: 3xx redirect not followed and error body scrubbed", flush=True)

        # Delegation checks: widening or TTL > parent rejected (403); narrowed child succeeds (200)
        del_url = f"{gateway_url}/mcp/poc/delegate"

        c, b = http_req(
            "POST",
            del_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", del_url, access_token=token),
            },
            body={
                "sub": "agent-child",
                "target_tool": "payments_list",
                "child_dpop_jwk": child_jwk,
                "allowed_tools": ["payments_list"],
                "arg_constraints": {"limit": {"type": "max_number", "max": 250.0}},
                "ttl_secs": 90,
            },
        )
        assert c == 403 and json.loads(b)["error"] == "child argument constraint widens parent constraint", (
            f"unexpected widened delegation response: {c}"
        )
        print("PASS: delegation widening parent constraint -> 403", flush=True)

        c, _ = http_req(
            "POST",
            del_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", del_url, access_token=token),
            },
            body={
                "sub": "agent-child",
                "target_tool": "payments_list",
                "child_dpop_jwk": child_jwk,
                "allowed_tools": ["payments_list"],
                "ttl_secs": 600,
            },
        )
        assert c == 403, f"TTL > parent expected 403, got {c}"
        print("PASS: delegation with TTL > parent exp -> 403", flush=True)

        c, b = http_req(
            "POST",
            del_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", del_url, access_token=token),
            },
            body={
                "sub": "agent-child",
                "target_tool": "payments_list",
                "child_dpop_jwk": child_jwk,
                "allowed_tools": ["payments_list"],
                "arg_constraints": {
                    "currency": {"type": "allowed_values", "values": ["EUR"]},
                    "limit": {"type": "max_number", "max": 25.0},
                },
                "ttl_secs": 120,
            },
        )
        assert c == 200, f"valid delegation failed: {c}"
        del_resp = json.loads(b)
        assert del_resp["iss"] == "stoa-poc-delegation"
        assert del_resp["aud"] == "mcp-tool:acme:payments_list"
        assert del_resp["depth"] == 1
        assert del_resp["tenant_id"] == "acme"
        child_tok = del_resp["access_token"]
        print("PASS: agent-parent delegated narrowed child token (iss=stoa-poc-delegation, aud=mcp-tool:acme:payments_list, depth=1)", flush=True)

    return token, child_tok


def run_child(
    gateway_url: str,
    upstream_ip: str,
    child_dpop: DpopKey,
    leaked_parent_token: str,
    child_token: str | None,
) -> None:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-child -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-child -> upstream-mock (IP)")

    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"agent-child /admin/health expected 404, got {code}"
    print("PASS: agent-child /admin/health -> 404", flush=True)

    assert "STOA_POC_BOOTSTRAP_SECRET" not in os.environ
    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    code, _ = http_req(
        "POST",
        boot_url,
        headers={"DPoP": child_dpop.sign_proof("POST", boot_url)},
        body={"sub": "agent-child", "tenant_id": "acme", "role": "reader"},
    )
    assert code == 401, f"agent-child bootstrap expected 401, got {code}"
    print("PASS: agent-child cannot bootstrap a parent token -> 401", flush=True)

    mcp_url = f"{gateway_url}/mcp/poc"
    code, _ = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {leaked_parent_token}",
            "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=leaked_parent_token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": {"currency": "EUR", "account": "acct-1", "limit": 10},
            },
        },
    )
    assert code == 401, f"agent-child parent token reuse expected 401, got {code}"
    print("PASS: agent-child cannot reuse parent token (DPoP cnf.jkt mismatch) -> 401", flush=True)

    if child_token is not None:
        # 1. Valid narrowed child call passes
        c, b = http_req(
            "POST",
            mcp_url,
            headers={
                "Authorization": f"DPoP {child_token}",
                "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_token),
            },
            body={
                "jsonrpc": "2.0",
                "id": 101,
                "method": "tools/call",
                "params": {
                    "name": "payments_list",
                    "arguments": {"currency": "EUR", "account": "acct-child-1", "limit": 20},
                },
            },
        )
        assert c == 200 and "error" not in json.loads(b) and "pay_001" in b, f"child call failed: {c} {b}"
        print("PASS: agent-child delegated call with conforming narrowed args succeeded", flush=True)

        # 2. All 3 argument constraint types enforced (allowed_values, prefix, max_number)
        for label, bad_args in [
            ("allowed_values (USD excluded for child)", {"currency": "USD", "account": "acct-1", "limit": 20}),
            ("prefix (missing acct-)", {"currency": "EUR", "account": "other-1", "limit": 20}),
            ("max_number (50 > child cap 25)", {"currency": "EUR", "account": "acct-1", "limit": 50}),
        ]:
            c, b = http_req(
                "POST",
                mcp_url,
                headers={
                    "Authorization": f"DPoP {child_token}",
                    "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_token),
                },
                body={
                    "jsonrpc": "2.0",
                    "id": 102,
                    "method": "tools/call",
                    "params": {"name": "payments_list", "arguments": bad_args},
                },
            )
            assert_role_denial(c, b)
            print(f"PASS: agent-child constraint denied ({label})", flush=True)

        # 3. Calling another tool mismatches child canonical resource `aud` -> 401
        c, b = http_req(
            "POST",
            mcp_url,
            headers={
                "Authorization": f"DPoP {child_token}",
                "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_token),
            },
            body={
                "jsonrpc": "2.0",
                "id": 103,
                "method": "tools/call",
                "params": {"name": "payments_redirect", "arguments": {}},
            },
        )
        assert_rpc_error(c, b, -32001, "Unauthorized", http_status=401)
        print("PASS: agent-child calling different tool rejected on audience mismatch -> 401", flush=True)

        # 4. Depth chain 1 -> 2 -> 3 succeeds, 3 -> 4 is rejected (403)
        del_url = f"{gateway_url}/mcp/poc/delegate"
        curr_tok = child_token
        for next_depth in (2, 3):
            c, b = http_req(
                "POST",
                del_url,
                headers={
                    "Authorization": f"DPoP {curr_tok}",
                    "DPoP": child_dpop.sign_proof("POST", del_url, access_token=curr_tok),
                },
                body={
                    "sub": f"agent-child-d{next_depth}",
                    "target_tool": "payments_list",
                    "child_dpop_jwk": child_dpop.jwk,
                    "allowed_tools": ["payments_list"],
                    "ttl_secs": 60,
                },
            )
            assert c == 200 and json.loads(b)["depth"] == next_depth, f"depth {next_depth} failed: {c}"
            curr_tok = json.loads(b)["access_token"]
        c, b = http_req(
            "POST",
            del_url,
            headers={
                "Authorization": f"DPoP {curr_tok}",
                "DPoP": child_dpop.sign_proof("POST", del_url, access_token=curr_tok),
            },
            body={
                "sub": "agent-child-d4",
                "target_tool": "payments_list",
                "child_dpop_jwk": child_dpop.jwk,
                "allowed_tools": ["payments_list"],
                "ttl_secs": 30,
            },
        )
        assert c == 403 and json.loads(b)["error"] == "delegation depth exceeds maximum of 3", (
            f"unexpected delegation depth response: {c}"
        )
        print("PASS: delegation depth bound 1 -> 2 -> 3 allowed, 3 -> 4 -> 403", flush=True)

        run_declared_limit_check(gateway_url, child_dpop, child_token)


def run_declared_limit_check(gateway: str, dpop: DpopKey, token: str) -> None:
    limits = read_my_limits(gateway, dpop, token)
    assert limits["role"] == "reader"
    assert limits["issued_policy_version"] == limits["policy_version"] == 1
    assert limits["allowed_tools"] == ["payments_list", "stoa_security"]
    rules = limits["argument_constraints"]["payments_list"]["limit"]
    assert {"type": "max_number", "max": 25.0} in rules
    assert_role_denial(*call_poc_tool(
        gateway, dpop, token, "payments_list",
        {"currency": "EUR", "account": "acct-child-1", "limit": 26},
    ))
    assert read_my_limits(gateway, dpop, token)["budgets"] == limits["budgets"]
    print("PASS: case 12 refuses the call above the child's declared limit", flush=True)


def run_role_update_checks(gateway: str, dpop: DpopKey, token_v1: str) -> None:
    # The same v1 token previously called payments_list successfully in run_parent.
    assert_role_denial(*call_poc_tool(
        gateway, dpop, token_v1, "payments_list",
        {"currency": "USD", "account": "acct-parent-1", "limit": 80},
    ))
    print("PASS: case 7 refuses withdrawn tool on the next call", flush=True)

    assert_role_denial(*call_poc_tool(gateway, dpop, token_v1, "payments_hidden", {}))
    old_limits = read_my_limits(gateway, dpop, token_v1)
    assert old_limits["issued_policy_version"] == 1 and old_limits["policy_version"] == 2
    assert "payments_list" not in old_limits["allowed_tools"]
    assert "payments_hidden" not in old_limits["allowed_tools"]
    token_v2 = bootstrap_parent(gateway, dpop)["access_token"]
    new_limits = read_my_limits(gateway, dpop, token_v2)
    assert new_limits["issued_policy_version"] == new_limits["policy_version"] == 2
    assert "payments_hidden" in new_limits["allowed_tools"]
    print("PASS: case 8 keeps the added tool outside the v1 token's scope", flush=True)


def run_jalon3_parent_phase1(
    gateway_url: str, upstream_ip: str, dpop: DpopKey, child_jwk: dict
) -> tuple[str, str, str]:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-parent -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-parent -> upstream-mock (IP)")

    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    code, body = http_req(
        "POST",
        boot_url,
        headers={
            "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
            "DPoP": dpop.sign_proof("POST", boot_url),
        },
        body={"sub": "agent-parent", "tenant_id": "acme", "role": "reader", "ttl_secs": 300},
    )
    assert code == 200, f"bootstrap chain A failed: {code}"
    boot = json.loads(body)
    token = boot["access_token"]
    chain_id = boot["chain_id"]

    mcp_url = f"{gateway_url}/mcp/poc"

    # 1. Filtered tools/list excludes `payments_hidden` (not in reader role)
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
        },
        body={"jsonrpc": "2.0", "id": 301, "method": "tools/list", "params": {}},
    )
    assert c == 200, f"tools/list failed: {c}"
    listed_names = [t["name"] for t in json.loads(b)["result"]["tools"]]
    assert "payments_list" in listed_names and "payments_hidden" not in listed_names, (
        f"tools/list did not filter out payments_hidden: {listed_names}"
    )
    print(f"PASS: tools/list filtered by role ({len(listed_names)} tools, payments_hidden excluded)", flush=True)

    # 2. Direct call to payments_hidden with spoofed X-Stoa-Source header denied (0 upstream calls)
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
            "X-Stoa-Source": "control-plane",
        },
        body={
            "jsonrpc": "2.0",
            "id": 302,
            "method": "tools/call",
            "params": {"name": "payments_hidden", "arguments": {}},
        },
    )
    assert_role_denial(c, b)
    print("PASS: direct call to payments_hidden denied (X-Stoa-Source ignored)", flush=True)

    # 3. poc/subcalls: step 1 (payments_list) succeeds [chain_A=1, caller=1], step 2 (payments_hidden) denied
    valid_args = {"currency": "EUR", "account": "acct-j3-1", "limit": 20}
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 303,
            "method": "poc/subcalls",
            "params": {
                "steps": [
                    {"name": "payments_list", "arguments": valid_args},
                    {"name": "payments_hidden", "arguments": {}},
                ]
            },
        },
    )
    assert_role_denial(c, b)
    print("PASS: poc/subcalls denied out-of-role step 2 (payments_hidden never reached)", flush=True)

    # 4. poc/subcalls fallback with invalid constraint args denied [payments_fail => chain_A=2, caller=2]
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 304,
            "method": "poc/subcalls",
            "params": {
                "steps": [
                    {
                        "name": "payments_fail",
                        "arguments": {},
                        "fallback": {
                            "name": "payments_list",
                            "arguments": {"currency": "GBP", "account": "acct-fb", "limit": 10},
                        },
                    }
                ]
            },
        },
    )
    assert c == 200 and "error" in json.loads(b), f"invalid fallback expected deny: {c}"
    print("PASS: poc/subcalls fallback violating argument constraint denied (0 upstream call)", flush=True)

    # 5. poc/subcalls fallback with valid args succeeds [payments_fail => 3, fallback payments_list => 4]
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 305,
            "method": "poc/subcalls",
            "params": {
                "steps": [
                    {
                        "name": "payments_fail",
                        "arguments": {},
                        "fallback": {
                            "name": "payments_list",
                            "arguments": valid_args,
                        },
                    }
                ]
            },
        },
    )
    assert c == 200, f"valid fallback failed: {c}"
    rpc = json.loads(b)
    assert "error" not in rpc and rpc["result"]["steps"][0]["fallback_used"] is True, "expected the conforming fallback to succeed"
    print("PASS: poc/subcalls fallback with conforming args succeeded", flush=True)

    # 6. Delegate child token on chain A
    del_url = f"{gateway_url}/mcp/poc/delegate"
    c, b = http_req(
        "POST",
        del_url,
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": dpop.sign_proof("POST", del_url, access_token=token),
        },
        body={
            "sub": "agent-child",
            "target_tool": "payments_list",
            "child_dpop_jwk": child_jwk,
            "allowed_tools": ["payments_list"],
            "arg_constraints": {
                "currency": {"type": "allowed_values", "values": ["EUR"]},
                "limit": {"type": "max_number", "max": 25.0},
            },
            "ttl_secs": 180,
        },
    )
    assert c == 200, f"delegation failed: {c}"
    child_tok = json.loads(b)["access_token"]
    print("PASS: agent-parent delegated chain A child token to agent-child", flush=True)
    return token, chain_id, child_tok


def run_jalon3_child_use(
    gateway_url: str, child_dpop: DpopKey, child_token: str
) -> None:
    mcp_url = f"{gateway_url}/mcp/poc"
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {child_token}",
            "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_token),
        },
        body={
            "jsonrpc": "2.0",
            "id": 310,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": {"currency": "EUR", "account": "acct-child-j3", "limit": 15},
            },
        },
    )
    assert c == 200 and "error" not in json.loads(b) and "pay_001" in b, f"child call failed: {c}"
    print("PASS: agent-child executed 1 valid call on chain A (chain_A=5/5, root caller=5/8)", flush=True)


def run_concurrent_calls(
    gateway_url: str, dpop: DpopKey, token: str, workers: int, label: str
) -> tuple[int, int, list[str]]:
    mcp_url = f"{gateway_url}/mcp/poc"
    barrier = threading.Barrier(workers)

    def one_call(idx: int) -> tuple[bool, str]:
        proof = dpop.sign_proof("POST", mcp_url, access_token=token)
        barrier.wait()
        c, b = http_req(
            "POST",
            mcp_url,
            headers={"Authorization": f"DPoP {token}", "DPoP": proof},
            body={
                "jsonrpc": "2.0",
                "id": 400 + idx,
                "method": "tools/call",
                "params": {
                    "name": "payments_list",
                    "arguments": {"currency": "EUR", "account": f"acct-race-{idx}", "limit": 10},
                },
            },
        )
        assert c == 200, f"{label} worker {idx} unexpected HTTP {c}:"
        rpc = json.loads(b)
        if "error" in rpc:
            return False, str(rpc["error"].get("message", ""))
        return True, "ok"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(one_call, range(workers)))

    admitted = sum(1 for ok, _ in outcomes if ok)
    denied_msgs = [msg for ok, msg in outcomes if not ok]
    return admitted, len(denied_msgs), denied_msgs


def run_jalon3_parent_revoke_and_race(
    gateway_url: str, dpop: DpopKey, token_a: str, chain_a: str
) -> str:
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]

    # 1. Atomically revoke chain A using parent DPoP token
    revoke_url = f"{gateway_url}/mcp/poc/revoke"
    c, b = http_req(
        "POST",
        revoke_url,
        headers={
            "Authorization": f"DPoP {token_a}",
            "DPoP": dpop.sign_proof("POST", revoke_url, access_token=token_a),
        },
        body={"chain_id": chain_a},
    )
    assert c == 200 and json.loads(b).get("revoked") is True, f"revoke failed: {c}"
    print(f"PASS: POST /mcp/poc/revoke atomically revoked {chain_a}", flush=True)

    # 2. Parent on chain A is immediately denied
    mcp_url = f"{gateway_url}/mcp/poc"
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token_a}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token_a),
        },
        body={
            "jsonrpc": "2.0",
            "id": 320,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": {"currency": "EUR", "account": "acct-revoked", "limit": 10},
            },
        },
    )
    assert c == 200 and "revoked" in b.lower(), f"revoked parent expected deny: {c}"
    print("PASS: agent-parent call on revoked chain A immediately denied", flush=True)

    # 3. Chain B for SAME caller (`agent-parent`, already used 5/8 across parent+child of chain A):
    #    16 concurrent HTTP threads -> exact 3 admitted, 13 denied (`Caller budget exceeded`).
    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    c, b = http_req(
        "POST",
        boot_url,
        headers={
            "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
            "DPoP": dpop.sign_proof("POST", boot_url),
        },
        body={"sub": "agent-parent", "tenant_id": "acme", "role": "reader", "ttl_secs": 300},
    )
    assert c == 200, f"bootstrap chain B failed: {c}"
    token_b = json.loads(b)["access_token"]

    ok_b, no_b, msgs_b = run_concurrent_calls(gateway_url, dpop, token_b, 16, "chain-B-caller-cap")
    assert ok_b == 3 and no_b == 13, f"chain B race expected 3 ok / 13 denied, got {ok_b}/{no_b}"
    assert all("caller budget" in m.lower() for m in msgs_b), "unexpected chain B admission status"
    print(
        "PASS: 16 concurrent HTTP calls on chain B (shared caller 5/8 used, chain cap 5) -> "
        "exact 3 admitted / 13 denied (Caller budget exceeded, 0 double debit)",
        flush=True,
    )

    # 4. Chain C for fresh caller (`agent-parent-race`, caller 0/8, chain C 0/5):
    #    16 concurrent HTTP threads -> exact 5 admitted, 11 denied (`Chain budget exceeded`).
    c, b = http_req(
        "POST",
        boot_url,
        headers={
            "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
            "DPoP": dpop.sign_proof("POST", boot_url),
        },
        body={"sub": "agent-parent-race", "tenant_id": "acme", "role": "reader", "ttl_secs": 300},
    )
    assert c == 200, f"bootstrap chain C failed: {c}"
    token_c = json.loads(b)["access_token"]

    ok_c, no_c, msgs_c = run_concurrent_calls(gateway_url, dpop, token_c, 16, "chain-C-chain-cap")
    assert ok_c == 5 and no_c == 11, f"chain C race expected 5 ok / 11 denied, got {ok_c}/{no_c}"
    assert all("chain budget" in m.lower() for m in msgs_c), "unexpected chain C admission status"
    print(
        "PASS: 16 concurrent HTTP calls on chain C (chain cap 5, caller cap 8) -> "
        "exact 5 admitted / 11 denied (Chain budget exceeded, 0 double debit)",
        flush=True,
    )

    return token_c


def run_jalon3_child_post_revoke(
    gateway_url: str, child_dpop: DpopKey, child_tok: str
) -> None:
    mcp_url = f"{gateway_url}/mcp/poc"
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {child_tok}",
            "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_tok),
        },
        body={
            "jsonrpc": "2.0",
            "id": 330,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": {"currency": "EUR", "account": "acct-child-revoked", "limit": 10},
            },
        },
    )
    assert c == 200 and "revoked" in b.lower(), f"revoked child expected deny: {c}"
    print("PASS: agent-child call on revoked chain A immediately denied (atomic cascade)", flush=True)


def run_jalon3_post_restart(gateway_url: str, dpop: DpopKey, token_c: str) -> None:
    mcp_url = f"{gateway_url}/mcp/poc"
    c, _ = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {token_c}",
            "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token_c),
        },
        body={"jsonrpc": "2.0", "id": 340, "method": "ping", "params": {}},
    )
    assert c == 401, f"pre-restart token after gateway restart expected 401, got {c}"
    print("PASS: pre-restart token rejected with 401 after real stoa-gateway restart (ephemeral RS256 rotated)", flush=True)


def run_revocation_saturation_parent(
    gateway_url: str, upstream_ip: str, child_jwk: dict
) -> str:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-parent -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-parent -> upstream-mock (IP)")

    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    revoke_url = f"{gateway_url}/mcp/poc/revoke"
    del_url = f"{gateway_url}/mcp/poc/delegate"
    mcp_url = f"{gateway_url}/mcp/poc"
    valid_args = {"currency": "EUR", "account": "acct-sat-1", "limit": 10}

    def bootstrap_parent(dpop: DpopKey, sub: str) -> tuple[int, dict]:
        c, b = http_req(
            "POST",
            boot_url,
            headers={
                "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
                "DPoP": dpop.sign_proof("POST", boot_url),
            },
            body={"sub": sub, "tenant_id": "acme", "role": "reader", "ttl_secs": 300},
        )
        return c, json.loads(b)

    def revoke_chain(dpop: DpopKey, token: str, chain_id: str) -> tuple[int, dict]:
        c, b = http_req(
            "POST",
            revoke_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", revoke_url, access_token=token),
            },
            body={"chain_id": chain_id},
        )
        return c, json.loads(b)

    def call_payments(dpop: DpopKey, token: str, req_id: int) -> tuple[int, dict]:
        c, b = http_req(
            "POST",
            mcp_url,
            headers={
                "Authorization": f"DPoP {token}",
                "DPoP": dpop.sign_proof("POST", mcp_url, access_token=token),
            },
            body={
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": "payments_list", "arguments": valid_args},
            },
        )
        return c, json.loads(b)

    dpop1, dpop2, dpop3, dpop4 = DpopKey(), DpopKey(), DpopKey(), DpopKey()

    c1, b1 = bootstrap_parent(dpop1, "agent-sat-1")
    assert c1 == 200, f"bootstrap chain 1 failed: {c1}"
    tok1, cid1 = b1["access_token"], b1["chain_id"]

    c2, b2 = bootstrap_parent(dpop2, "agent-sat-2")
    assert c2 == 200, f"bootstrap chain 2 failed: {c2}"
    tok2, cid2 = b2["access_token"], b2["chain_id"]

    c3, b3 = bootstrap_parent(dpop3, "agent-sat-3")
    assert c3 == 200, f"bootstrap chain 3 failed: {c3}"
    tok3, cid3 = b3["access_token"], b3["chain_id"]
    print("PASS: bootstrapped 3 parent chains before saturation", flush=True)

    # Baseline call on chain 3 proves the route and upstream work before saturation.
    c, rpc = call_payments(dpop3, tok3, 501)
    assert c == 200 and "error" not in rpc and "pay_001" in json.dumps(rpc), (
        f"baseline call on chain 3 failed: {c}"
    )
    print("PASS: pre-saturation baseline call on chain 3 succeeded", flush=True)

    # Delegate a child token on chain 3 before saturation to verify child fail-closed too.
    c, b = http_req(
        "POST",
        del_url,
        headers={
            "Authorization": f"DPoP {tok3}",
            "DPoP": dpop3.sign_proof("POST", del_url, access_token=tok3),
        },
        body={
            "sub": "agent-child",
            "target_tool": "payments_list",
            "child_dpop_jwk": child_jwk,
            "allowed_tools": ["payments_list"],
            "ttl_secs": 120,
        },
    )
    assert c == 200, f"pre-saturation delegation on chain 3 failed: {c}"
    child_tok = json.loads(b)["access_token"]

    # Revoke chain 1 (1/2) and confirm it is denied immediately.
    rc1, rb1 = revoke_chain(dpop1, tok1, cid1)
    assert rc1 == 200 and rb1.get("revoked") is True, f"revoke chain 1 failed: {rc1}"
    c, rpc = call_payments(dpop1, tok1, 502)
    assert c == 200 and rpc.get("error", {}).get("code") == -32003, (
        f"expected Chain revoked on chain 1: {c} {rpc.get('error')}"
    )
    assert rpc["error"].get("message") == "Chain revoked"
    print("PASS: chain 1 revoked (1/2) and denied immediately", flush=True)

    # Revoke chain 2 (2/2): revocation table is now saturated.
    rc2, rb2 = revoke_chain(dpop2, tok2, cid2)
    assert rc2 == 200 and rb2.get("revoked") is True, f"revoke chain 2 failed: {rc2}"
    print("PASS: chain 2 revoked (2/2, revocation table saturated)", flush=True)

    # 3rd revoke fails closed with 503 and revocation_table_full.
    rc3, rb3 = revoke_chain(dpop3, tok3, cid3)
    assert rc3 == 503 and rb3.get("error") == "revocation_table_full", (
        f"3rd revoke expected 503 revocation_table_full, got {rc3} {rb3.get('error')}"
    )
    print("PASS: 3rd revoke refused with 503 revocation_table_full", flush=True)

    # Delegation on chain 3 and 4th bootstrap both fail closed with 503 saturation reason.
    dc, db = http_req(
        "POST",
        del_url,
        headers={
            "Authorization": f"DPoP {tok3}",
            "DPoP": dpop3.sign_proof("POST", del_url, access_token=tok3),
        },
        body={
            "sub": "agent-child-blocked",
            "target_tool": "payments_list",
            "child_dpop_jwk": child_jwk,
            "allowed_tools": ["payments_list"],
            "ttl_secs": 60,
        },
    )
    djson = json.loads(db)
    assert dc == 503 and djson.get("error") == "revocation table is saturated; failing closed", (
        f"saturated delegate expected 503, got {dc} {djson.get('error')}"
    )

    c4, b4 = bootstrap_parent(dpop4, "agent-sat-4")
    assert c4 == 503 and b4.get("error") == "revocation table is saturated; failing closed", (
        f"saturated bootstrap expected 503, got {c4} {b4.get('error')}"
    )
    print(
        "PASS: saturated delegate and bootstrap refused with 503 "
        "(revocation table is saturated; failing closed)",
        flush=True,
    )

    # Tool call on non-revoked chain 3 fails closed without reaching upstream.
    c, rpc = call_payments(dpop3, tok3, 503)
    assert c == 200 and rpc.get("error", {}).get("code") == -32005, (
        f"chain 3 expected -32005 Admission unavailable, got {c} {rpc.get('error')}"
    )
    assert rpc["error"].get("message") == "Admission unavailable"
    print("PASS: non-revoked chain 3 tool call refused fail-closed (-32005)", flush=True)

    # Previously revoked chains stay refused without reaching upstream.
    for label, dpop, tok, req_id in [
        ("chain 1", dpop1, tok1, 504),
        ("chain 2", dpop2, tok2, 505),
    ]:
        c, rpc = call_payments(dpop, tok, req_id)
        assert c == 200 and rpc.get("error", {}).get("code") == -32005, (
            f"revoked {label} expected -32005 under saturation, got {c} {rpc.get('error')}"
        )
        assert rpc["error"].get("message") == "Admission unavailable"
    print("PASS: revoked chains 1 and 2 stay refused under table saturation", flush=True)

    return child_tok


def run_revocation_saturation_child(
    gateway_url: str, child_dpop: DpopKey, child_tok: str
) -> None:
    mcp_url = f"{gateway_url}/mcp/poc"
    c, b = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {child_tok}",
            "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=child_tok),
        },
        body={
            "jsonrpc": "2.0",
            "id": 510,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": {"currency": "EUR", "account": "acct-sat-child", "limit": 10},
            },
        },
    )
    rpc = json.loads(b)
    assert c == 200 and rpc.get("error", {}).get("code") == -32005, (
        f"child on saturated table expected -32005, got {c} {rpc.get('error')}"
    )
    assert rpc["error"].get("message") == "Admission unavailable"
    print(
        "PASS: agent-child call on non-revoked chain 3 refused fail-closed under table saturation",
        flush=True,
    )
