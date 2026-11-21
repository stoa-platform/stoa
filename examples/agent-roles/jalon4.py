#!/usr/bin/env python3
"""Exercise the local MCP projection from the two isolated agent containers."""

from contextlib import redirect_stdout
import json
import os
import sys
import urllib.error
import urllib.request

from agent_harness import DpopKey, assert_tcp_unreachable, http_req
from agent_pipes import agent_pair, emit, receive, send


PAYMENT = {"account": "acct-child-example", "currency": "EUR", "limit": 20}


def note(message: str) -> None:
    # The standard output of each agent is reserved for its private pipe.
    print(f"PASS: {message}", file=sys.stderr, flush=True)


def check_isolation(gateway: str, mock_ip: str, label: str) -> None:
    with redirect_stdout(sys.stderr):
        assert_tcp_unreachable(os.environ["UPSTREAM_MOCK_HOST"], 9000, f"{label} DNS")
        assert_tcp_unreachable(mock_ip, 9000, f"{label} IP")
    code, _ = http_req("GET", f"{gateway}/admin/health")
    assert code == 404, f"{label} must not reach /admin/health"


def headers_for(url: str, key: DpopKey, token: str) -> dict:
    return {"Authorization": f"DPoP {token}", "DPoP": key.sign_proof("POST", url, token)}


def bootstrap(gateway: str, key: DpopKey, sub: str) -> dict:
    url = f"{gateway}/mcp/poc/bootstrap"
    code, body = http_req(
        "POST",
        url,
        headers={
            "DPoP": key.sign_proof("POST", url),
            "X-Stoa-Poc-Bootstrap-Secret": os.environ["STOA_POC_BOOTSTRAP_SECRET"],
        },
        body={"sub": sub, "tenant_id": "acme", "role": "reader", "ttl_secs": 180},
    )
    assert code == 200, f"bootstrap returned HTTP {code}"
    return json.loads(body)


def rpc(mcp_url: str, key: DpopKey, token: str, method: str, params: dict) -> tuple:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    request = urllib.request.Request(
        mcp_url,
        method="POST",
        headers={"Content-Type": "application/json", **headers_for(mcp_url, key, token)},
        data=body.encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers.get("Cache-Control"), json.load(response)
    except urllib.error.HTTPError as response:
        with response:
            return response.code, response.headers.get("Cache-Control"), json.load(response)


def call(mcp_url: str, key: DpopKey, token: str, name: str, args: dict) -> tuple:
    return rpc(mcp_url, key, token, "tools/call", {"name": name, "arguments": args})


def check_limits(
    url: str, key: DpopKey, token: str, chain: int, caller: int, depth: int
) -> dict:
    status, cache_control, payload = call(url, key, token, "stoa_security", {})
    assert status == 200 and "result" in payload, f"limits request failed with HTTP {status}"
    directives = [part.strip() for part in (cache_control or "").lower().split(",")]
    assert "no-store" in directives, "limits must not be cached"
    result = payload["result"]
    view = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == view, "MCP payloads differ"
    assert set(view) == {"role", "allowed_tools", "argument_constraints", "budget", "delegation_depth"}
    assert view["role"] == {"name": "reader", "policy_version": 1}
    assert view["budget"] == {"chain_remaining": chain, "root_caller_remaining": caller}
    assert view["delegation_depth"] == depth
    return view


def check_constraints(view: dict, currencies: set[str], prefix: str, limit: float) -> None:
    assert set(view["argument_constraints"]) == {"payments_list"}
    fields = view["argument_constraints"]["payments_list"]
    assert set(fields) == {"currency", "account", "limit"}
    allowed = [set(rule["values"]) for rule in fields["currency"] if rule["type"] == "allowed_values"]
    assert allowed and set.intersection(*allowed) == currencies
    prefixes = [rule["prefix"] for rule in fields["account"] if rule["type"] == "prefix"]
    assert prefixes and max(prefixes, key=len) == prefix
    ceilings = [rule["max"] for rule in fields["limit"] if rule["type"] == "max_number"]
    assert ceilings and min(ceilings) == limit


def spend(url: str, key: DpopKey, token: str) -> None:
    status, _, body = call(url, key, token, "payments_list", PAYMENT)
    assert status == 200 and "result" in body and "pay_001" in json.dumps(body["result"]), (
        f"payment read failed with HTTP {status}"
    )


def parent(gateway: str, mock_ip: str) -> None:
    child_jwk = receive(sys.stdin)["jwk"]
    check_isolation(gateway, mock_ip, "parent agent")
    key_a, key_b = DpopKey(), DpopKey()
    chain_a = bootstrap(gateway, key_a, "jalon4-caller-a")
    token_a = chain_a["access_token"]
    token_b = bootstrap(gateway, key_b, "jalon4-caller-b")["access_token"]
    mcp = f"{gateway}/mcp/poc"

    code, _, listing = rpc(mcp, key_a, token_a, "tools/list", {})
    assert code == 200 and "result" in listing
    projection = [tool for tool in listing["result"]["tools"] if tool["name"] == "stoa_security"]
    assert len(projection) == 1
    definition = projection[0]
    assert "Read your current access and remaining budgets" in definition["description"]
    assert definition["annotations"]["readOnlyHint"] is True
    assert definition["inputSchema"]["additionalProperties"] is False
    assert definition["outputSchema"]["type"] == "object"
    note("UAC projects stoa_security with read-only metadata and a closed input schema")

    initial = check_limits(mcp, key_a, token_a, 2, 3, 0)
    assert initial["allowed_tools"] == [
        "payments_fail", "payments_list", "payments_outbound_blocked", "payments_redirect",
    ]
    check_constraints(initial, {"EUR", "USD"}, "acct-", 100.0)
    status, _, wrong_owner = call(mcp, key_b, token_a, "stoa_security", {})
    assert status == 401 and "error" in wrong_owner
    status, _, other_tenant = call(mcp, key_a, token_a, "stoa_security", {"tenant_id": "other"})
    assert status == 200 and "error" in other_tenant
    note("stoa_security rejects a tenant selector and requires the caller's DPoP proof")

    spend(mcp, key_a, token_a)
    check_limits(mcp, key_a, token_a, 1, 2, 0)
    check_limits(mcp, key_b, token_b, 2, 3, 0)
    token_a2 = bootstrap(gateway, key_a, "jalon4-caller-a")["access_token"]
    check_limits(mcp, key_a, token_a2, 2, 2, 0)
    note("per-caller no-store limits reflect a debit without sharing either budget across callers")

    delegate = f"{gateway}/mcp/poc/delegate"
    status, body = http_req(
        "POST",
        delegate,
        headers=headers_for(delegate, key_a, token_a),
        body={
            "sub": "jalon4-child",
            "target_tool": "payments_list",
            "child_dpop_jwk": child_jwk,
            "allowed_tools": ["payments_list"],
            "arg_constraints": {
                "account": {"type": "prefix", "prefix": "acct-child-"},
                "currency": {"type": "allowed_values", "values": ["EUR"]},
                "limit": {"type": "max_number", "max": 25.0},
            },
            "ttl_secs": 120,
        },
    )
    assert status == 200, f"delegation returned HTTP {status}"
    delegated = json.loads(body)
    assert delegated["depth"] == 1 and delegated["aud"] == "mcp-tool:acme:payments_list"
    emit({"token": delegated["access_token"]})

    receive(sys.stdin)
    check_limits(mcp, key_a, token_a, 0, 1, 0)
    check_limits(mcp, key_a, token_a2, 2, 1, 0)
    check_limits(mcp, key_b, token_b, 2, 3, 0)
    note("parent sees the child's debit on the chain and root budget across its own chains")

    revoke = f"{gateway}/mcp/poc/revoke"
    status, _ = http_req(
        "POST", revoke, headers_for(revoke, key_a, token_a), {"chain_id": chain_a["chain_id"]}
    )
    assert status == 200, f"revocation returned HTTP {status}"
    status, _, revoked = call(mcp, key_a, token_a, "stoa_security", {})
    assert status == 200 and "error" in revoked
    check_limits(mcp, key_a, token_a2, 2, 1, 0)
    emit({})


def child(gateway: str, mock_ip: str) -> None:
    key = DpopKey()
    emit({"jwk": key.jwk})
    check_isolation(gateway, mock_ip, "child agent")
    token = receive(sys.stdin)["token"]
    mcp = f"{gateway}/mcp/poc"

    view = check_limits(mcp, key, token, 1, 2, 1)
    assert view["allowed_tools"] == ["payments_list"]
    check_constraints(view, {"EUR"}, "acct-child-", 25.0)
    status, _, denied = call(mcp, key, token, "payments_list", {**PAYMENT, "limit": 26})
    assert status == 200 and "error" in denied
    spend(mcp, key, token)
    check_limits(mcp, key, token, 0, 1, 1)
    note("child limits show canonical scope, narrowed constraints, depth and exhausted chain budget")
    emit({})

    receive(sys.stdin)
    status, _, revoked = call(mcp, key, token, "stoa_security", {})
    assert status == 200 and "error" in revoked
    note("revocation closes the limits view for both parent and child")


def orchestrate(mock_ip: str) -> None:
    with agent_pair("/app/jalon4.py", mock_ip) as (parent_agent, child_agent):
        send(parent_agent.stdin, receive(child_agent.stdout))
        send(child_agent.stdin, receive(parent_agent.stdout))
        send(parent_agent.stdin, receive(child_agent.stdout))
        send(child_agent.stdin, receive(parent_agent.stdout))


if __name__ == "__main__":
    mode, mock_ip = sys.argv[1:]
    if mode == "host":
        orchestrate(mock_ip)
    else:
        {"parent": parent, "child": child}[mode](os.environ["STOA_GATEWAY_URL"], mock_ip)
