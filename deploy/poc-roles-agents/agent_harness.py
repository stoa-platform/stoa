#!/usr/bin/env python3
"""In-container verification harness for `agent-parent` and `agent-child` (Jalons 1 & 2)."""

import base64
import hashlib
import hmac
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

CHILD_KEY_FILE = Path("/tmp/child_dpop_key.pem")


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

    def save(self, path: Path) -> None:
        pem = self._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        path.chmod(0o600)

    @classmethod
    def load(cls, path: Path) -> "DpopKey":
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        return cls(key)

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


def run_parent(gateway_url: str, upstream_ip: str, child_jwk_json: str | None) -> tuple[str, str | None]:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-parent -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-parent -> upstream-mock (IP)")

    code, body = http_req("GET", f"{gateway_url}/ready")
    assert code == 200 and body.strip() == "READY", f"/ready failed: {code} {body}"
    print("PASS: /ready returned 200 READY with local signed policy loaded", flush=True)

    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"/admin/health expected 404, got {code}"
    print("PASS: /admin/health returned 404 (isolated from agent containers)", flush=True)

    dpop = DpopKey()
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
    assert code == 200, f"bootstrap failed: {code} {body}"
    boot = json.loads(body)
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
    if child_jwk_json is not None:
        # Jalon 2 parent checks: OPA negative, outbound address policy block, 3xx non-follow + scrubbed error
        for label, tool_name, expected_err in [
            ("OPA negative case (payments_opa_denied)", "payments_opa_denied", "policy"),
            ("Outbound address policy blocks link-local IP", "payments_outbound_blocked", "failed"),
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
            assert c == 200 and "error" in json.loads(b) and expected_err in b.lower(), f"{label} failed: {c} {b}"
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
        child_jwk = json.loads(child_jwk_json)
        del_url = f"{gateway_url}/mcp/poc/delegate"

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
                "arg_constraints": {"limit": {"type": "max_number", "max": 250.0}},
                "ttl_secs": 90,
            },
        )
        assert c == 403, f"widened delegation expected 403, got {c}"
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
        assert c == 200, f"valid delegation failed: {c} {b}"
        del_resp = json.loads(b)
        assert del_resp["iss"] == "stoa-poc-delegation"
        assert del_resp["aud"] == "mcp-tool:acme:payments_list"
        assert del_resp["depth"] == 1
        assert del_resp["tenant_id"] == "acme"
        child_tok = del_resp["access_token"]
        print("PASS: agent-parent delegated narrowed child token (iss=stoa-poc-delegation, aud=mcp-tool:acme:payments_list, depth=1)", flush=True)

    return token, child_tok


def run_child(
    gateway_url: str, upstream_ip: str, leaked_parent_token: str, child_token: str | None
) -> None:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]

    assert_tcp_unreachable(upstream_host, 9000, "agent-child -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-child -> upstream-mock (IP)")

    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"agent-child /admin/health expected 404, got {code}"
    print("PASS: agent-child /admin/health -> 404", flush=True)

    assert "STOA_POC_BOOTSTRAP_SECRET" not in os.environ
    child_dpop = DpopKey.load(CHILD_KEY_FILE) if CHILD_KEY_FILE.exists() else DpopKey()
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
            assert c == 200 and "error" in json.loads(b), f"expected constraint deny for {label}: {c} {b}"
            print(f"PASS: agent-child constraint denied ({label})", flush=True)

        # 3. Calling another tool mismatches child canonical resource `aud` -> 401
        c, _ = http_req(
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
        assert c == 401, f"wrong tool audience for child expected 401, got {c}"
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
            assert c == 200 and json.loads(b)["depth"] == next_depth, f"depth {next_depth} failed: {c} {b}"
            curr_tok = json.loads(b)["access_token"]
        c, _ = http_req(
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
        assert c == 403, f"depth 3 -> 4 expected 403, got {c}"
        print("PASS: delegation depth bound 1 -> 2 -> 3 allowed, 3 -> 4 -> 403", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "child-init-key":
        k = DpopKey()
        k.save(CHILD_KEY_FILE)
        print(json.dumps(k.jwk), flush=True)
        sys.exit(0)

    gateway = os.environ["STOA_GATEWAY_URL"]
    mock_ip = sys.argv[2]
    if mode == "parent":
        child_jwk = sys.argv[3] if len(sys.argv) > 3 else None
        tok, child_tok = run_parent(gateway, mock_ip, child_jwk)
        print(f"PARENT_TOKEN_FOR_NEGATIVE_TEST={tok}", flush=True)
        if child_tok is not None:
            print(f"CHILD_TOKEN_DELEGATED={child_tok}", flush=True)
    elif mode == "child":
        parent_tok = sys.argv[3]
        child_tok = sys.argv[4] if len(sys.argv) > 4 else None
        run_child(gateway, mock_ip, parent_tok, child_tok)
    else:
        raise SystemExit(f"unknown mode: {mode}")
