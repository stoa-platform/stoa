#!/usr/bin/env python3
"""In-container verification harness for `agent-parent` and `agent-child` (Jalon 1)."""

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

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def int_to_b64url(n: int, length: int | None = None) -> str:
    byte_len = length if length is not None else max(1, (n.bit_length() + 7) // 8)
    return b64url(n.to_bytes(byte_len, "big"))


class DpopKey:
    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
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


def run_parent(gateway_url: str, upstream_ip: str) -> str:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]
    bootstrap_secret = os.environ["STOA_POC_BOOTSTRAP_SECRET"]

    # 1. Network isolation: upstream-mock unreachable by DNS name AND by IP
    assert_tcp_unreachable(upstream_host, 9000, "agent-parent -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-parent -> upstream-mock (IP)")

    # 2. /ready is 200 READY and /admin/* is isolated (404)
    code, body = http_req("GET", f"{gateway_url}/ready")
    assert code == 200 and body.strip() == "READY", f"/ready failed: {code} {body}"
    print("PASS: /ready returned 200 READY with local signed policy loaded", flush=True)

    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"/admin/health expected 404, got {code}"
    print("PASS: /admin/health returned 404 (isolated from agent containers)", flush=True)

    # 3. Bootstrap parent token with DPoP proof
    dpop = DpopKey()
    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    code, body = http_req(
        "POST",
        boot_url,
        headers={
            "X-Stoa-Poc-Bootstrap-Secret": bootstrap_secret,
            "DPoP": dpop.sign_proof("POST", boot_url),
        },
        body={"sub": "agent-parent", "tenant_id": "acme", "role": "reader"},
    )
    assert code == 200, f"bootstrap failed: {code} {body}"
    boot = json.loads(body)
    token = boot["access_token"]
    kid = boot["kid"]
    assert boot["token_type"] == "DPoP" and boot["depth"] == 0
    print(f"PASS: agent-parent bootstrapped RS256 DPoP token (kid={kid})", flush=True)

    # 4. Positive MCP tools/call with DPoP proof -> hits upstream-mock via gateway
    mcp_url = f"{gateway_url}/mcp/poc"
    call_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "payments_list", "arguments": {}},
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
    assert "pay_001" in body, f"expected upstream mock payload, got: {body}"
    print("PASS: agent-parent MCP tools/call with DPoP succeeded via gateway", flush=True)

    # 5. Negative auth checks (all must be 401 and send ZERO requests upstream)
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

    return token


def run_child(gateway_url: str, upstream_ip: str, leaked_parent_token: str) -> None:
    upstream_host = os.environ["UPSTREAM_MOCK_HOST"]

    # 1. Network isolation: upstream-mock unreachable by DNS name AND by IP
    assert_tcp_unreachable(upstream_host, 9000, "agent-child -> upstream-mock (DNS)")
    assert_tcp_unreachable(upstream_ip, 9000, "agent-child -> upstream-mock (IP)")

    # 2. /admin/* unreachable
    code, _ = http_req("GET", f"{gateway_url}/admin/health")
    assert code == 404, f"agent-child /admin/health expected 404, got {code}"
    print("PASS: agent-child /admin/health -> 404", flush=True)

    # 3. Child has no bootstrap secret and cannot mint a parent token
    assert "STOA_POC_BOOTSTRAP_SECRET" not in os.environ
    child_dpop = DpopKey()
    boot_url = f"{gateway_url}/mcp/poc/bootstrap"
    code, _ = http_req(
        "POST",
        boot_url,
        headers={"DPoP": child_dpop.sign_proof("POST", boot_url)},
        body={"sub": "agent-child", "tenant_id": "acme", "role": "reader"},
    )
    assert code == 401, f"agent-child bootstrap expected 401, got {code}"
    print("PASS: agent-child cannot bootstrap a parent token -> 401", flush=True)

    # 4. Even if agent-child obtains parent's JWT, DPoP cnf.jkt binding rejects it
    mcp_url = f"{gateway_url}/mcp/poc"
    call_body = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "payments_list", "arguments": {}},
    }
    code, _ = http_req(
        "POST",
        mcp_url,
        headers={
            "Authorization": f"DPoP {leaked_parent_token}",
            "DPoP": child_dpop.sign_proof("POST", mcp_url, access_token=leaked_parent_token),
        },
        body=call_body,
    )
    assert code == 401, f"agent-child parent token reuse expected 401, got {code}"
    print("PASS: agent-child cannot reuse parent token (DPoP cnf.jkt mismatch) -> 401", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    gateway = os.environ["STOA_GATEWAY_URL"]
    mock_ip = sys.argv[2]
    if mode == "parent":
        tok = run_parent(gateway, mock_ip)
        # Emit token on stdout marker line ONLY for in-memory handoff to child negative test.
        print(f"PARENT_TOKEN_FOR_NEGATIVE_TEST={tok}", flush=True)
    elif mode == "child":
        parent_tok = sys.argv[3]
        run_child(gateway, mock_ip, parent_tok)
    else:
        raise SystemExit(f"unknown mode: {mode}")
