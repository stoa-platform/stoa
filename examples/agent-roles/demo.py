"""Demonstrate a refund through the isolated Compose agents and mock."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from agent_pipes import agent_pair, emit, receive, send

DpopKey: Any = None
http_req: Any = None
call: Any = None
headers_for: Any = None


def _load_container_deps() -> None:
    global DpopKey, http_req, call, headers_for
    if DpopKey is None:
        from agent_harness import DpopKey as _DpopKey, http_req as _http_req
        from jalon4 import call as _call, headers_for as _headers_for
        DpopKey = _DpopKey
        http_req = _http_req
        call = _call
        headers_for = _headers_for

TOOL = "refunds_create"
ROLE = "refund_operator"
PARENT_LIMIT = 500
CHILD_LIMIT = 50
DELEGATED_CUSTOMER = "C-1042"
OTHER_CUSTOMER = "C-2077"
EVIDENCE_HEADER = "X-Stoa-Poc-Decision-Evidence"


def show(step: str) -> None:
    # stdout carries only private synchronization messages inside containers.
    print(step, file=sys.stderr, flush=True)


def record(
    trace: list | None,
    step: str,
    status: int,
    error: dict | None = None,
    *,
    decision_id: str | None = None,
    evidence: dict | None = None,
) -> None:
    if trace is None:
        return
    entry: dict = {"step": step, "http_status": int(status)}
    if decision_id is not None:
        entry["decision_id"] = decision_id
    if error is not None:
        code = error.get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            entry["error_code"] = code
        entry["error_message"] = str(error["message"])
    if evidence is not None:
        entry["evidence"] = evidence
    trace.append(entry)


def refund_args(amount: int, customer: str) -> dict:
    return {"customer_id": customer, "amount_eur": amount, "currency": "EUR"}


def call_with_evidence(mcp_url: str, key: DpopKey, token: str, name: str, args: dict) -> tuple:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    )
    request = urllib.request.Request(
        mcp_url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            EVIDENCE_HEADER: "1",
            **headers_for(mcp_url, key, token),
        },
        data=body.encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers.get("Cache-Control"), json.load(response)
    except urllib.error.HTTPError as response:
        with response:
            return response.code, response.headers.get("Cache-Control"), json.load(response)


def check_limits(
    mcp: str,
    key: DpopKey,
    token: str,
    *,
    amount: int,
    customer: str | None,
    chain: int,
    caller: int,
    depth: int,
    trace: list | None = None,
    step: str = "",
) -> dict:
    status, cache_control, payload = call(mcp, key, token, "stoa_security", {})
    assert status == 200
    assert "no-store" in (cache_control or "").lower()
    result = payload["result"]
    view = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == view
    assert view["role"] == {"name": ROLE, "policy_version": 1}
    assert view["allowed_tools"] == [TOOL]
    assert view["budget"] == {"chain_remaining": chain, "root_caller_remaining": caller}
    assert view["delegation_depth"] == depth

    fields = view["argument_constraints"][TOOL]
    assert min(rule["max"] for rule in fields["amount_eur"]) == amount
    assert all(rule["values"] == ["EUR"] for rule in fields["currency"])
    if customer is not None:
        assert fields["customer_id"] == [{"type": "allowed_values", "values": [customer]}]
    else:
        assert "customer_id" not in fields
    record(trace, step, status)
    return view


def refund(
    mcp: str, key: DpopKey, token: str, amount: int, customer: str,
    *, trace: list | None = None, step: str = "",
) -> None:
    args = refund_args(amount, customer)
    status, _, payload = call(mcp, key, token, TOOL, args)
    assert status == 200
    result = payload["result"]
    assert not result.get("isError")
    assert json.loads(result["content"][0]["text"]) == {**args, "status": "simulated"}
    record(trace, step, status)


def refund_with_evidence(
    mcp: str, key: DpopKey, token: str, amount: int, customer: str,
    *, trace: list, step: str,
) -> str:
    args = refund_args(amount, customer)
    status, _, payload = call_with_evidence(mcp, key, token, TOOL, args)
    assert status == 200
    result = payload["result"]
    assert not result.get("isError")
    content = result["content"]
    assert len(content) == 2
    assert json.loads(content[0]["text"]) == {**args, "status": "simulated"}
    receipt = content[1]["text"]
    assert receipt.startswith("decision_id=")
    decision_id = receipt.split("=", 1)[1]
    record(trace, step, status, decision_id=decision_id)
    return decision_id


def reject_refund(
    mcp: str, key: DpopKey, token: str, amount: int, customer: str, reason: str,
    *, trace: list | None = None, step: str = "",
) -> None:
    status, _, payload = call(mcp, key, token, TOOL, refund_args(amount, customer))
    assert status == 200 and payload["error"]["message"] == reason
    record(trace, step, status, payload["error"])


def reject_refund_with_evidence(
    mcp: str, key: DpopKey, token: str, amount: int, customer: str, reason: str,
    *, trace: list, step: str,
) -> tuple[str, dict]:
    status, _, payload = call_with_evidence(mcp, key, token, TOOL, refund_args(amount, customer))
    assert status == 200
    error = payload["error"]
    assert error["message"] == reason
    data = error.get("data")
    assert isinstance(data, dict) and isinstance(data.get("decision_id"), str)
    record(trace, step, status, error, decision_id=data["decision_id"], evidence=data)
    return data["decision_id"], data


def _bootstrap_parent(gateway: str, key: DpopKey) -> tuple[int, dict]:
    bootstrap = f"{gateway}/mcp/poc/bootstrap"
    status, body = http_req(
        "POST",
        bootstrap,
        {
            "DPoP": key.sign_proof("POST", bootstrap),
            "X-Stoa-Poc-Bootstrap-Secret": os.environ["STOA_POC_BOOTSTRAP_SECRET"],
        },
        {"sub": "demo-parent", "tenant_id": "acme", "role": ROLE, "ttl_secs": 180},
    )
    assert status == 200
    return status, json.loads(body)


def _delegate_child(gateway: str, key: DpopKey, token: str, child_jwk: dict) -> tuple[int, dict]:
    delegate = f"{gateway}/mcp/poc/delegate"
    status, body = http_req(
        "POST",
        delegate,
        headers_for(delegate, key, token),
        {
            "sub": "demo-child",
            "target_tool": TOOL,
            "child_dpop_jwk": child_jwk,
            "allowed_tools": [TOOL],
            "arg_constraints": {
                "customer_id": {"type": "allowed_values", "values": [DELEGATED_CUSTOMER]},
                "amount_eur": {"type": "max_number", "max": CHILD_LIMIT},
            },
            "ttl_secs": 120,
        },
    )
    assert status == 200
    delegated = json.loads(body)
    assert delegated["depth"] == 1 and delegated["aud"] == f"mcp-tool:acme:{TOOL}"
    return status, delegated


def parent(gateway: str, mode: str = "") -> None:
    show_mode = mode == "show"
    preview_mode = mode == "preview"
    trace: list | None = [] if (show_mode or preview_mode) else None
    child_jwk = receive(sys.stdin)["jwk"]
    key = DpopKey()
    mcp = f"{gateway}/mcp/poc"
    status, session = _bootstrap_parent(gateway, key)
    token = session["access_token"]
    record(trace, "bootstrap", status)

    if not preview_mode:
        check_limits(
            mcp, key, token, amount=PARENT_LIMIT, customer=None, chain=2, caller=3, depth=0,
            trace=trace, step="parent_limits",
        )
        reject_refund(
            mcp, key, token, PARENT_LIMIT + 1, OTHER_CUSTOMER, "Tool call rejected by role policy",
            trace=trace, step="parent_over_limit",
        )
        refund(mcp, key, token, PARENT_LIMIT, OTHER_CUSTOMER, trace=trace, step="parent_refund")
        if not show_mode:
            show(f"1/6  Parent · rôle signé {ROLE}, plafond {PARENT_LIMIT} €, {PARENT_LIMIT} € acceptés")

    status, delegated = _delegate_child(gateway, key, token, child_jwk)
    record(trace, "delegate", status)
    if not show_mode and not preview_mode:
        show(f"2/6  Délégation · {TOOL}, {DELEGATED_CUSTOMER} uniquement, plafond {CHILD_LIMIT} €")
    msg: dict = {"token": delegated["access_token"]}
    if trace is not None:
        msg["trace"], trace = trace, []
    emit(msg)

    receive(sys.stdin)
    revoke = f"{mcp}/revoke"
    status, _ = http_req(
        "POST", revoke, headers_for(revoke, key, token), {"chain_id": session["chain_id"]}
    )
    assert status == 200
    record(trace, "revoke", status)
    emit({"trace": trace} if trace is not None else {})


def child(gateway: str, mode: str = "") -> None:
    show_mode = mode == "show"
    preview_mode = mode == "preview"
    trace: list | None = [] if (show_mode or preview_mode) else None
    key = DpopKey()
    emit({"jwk": key.jwk})
    token = receive(sys.stdin)["token"]
    mcp = f"{gateway}/mcp/poc"
    policy_denial = "Tool call rejected by role policy"

    if preview_mode:
        assert trace is not None
        check_limits(
            mcp, key, token, amount=CHILD_LIMIT, customer=DELEGATED_CUSTOMER,
            chain=2, caller=3, depth=1, trace=trace, step="child_limits",
        )
        refund_with_evidence(mcp, key, token, CHILD_LIMIT, DELEGATED_CUSTOMER, trace=trace, step="child_refund_50")
        reject_refund_with_evidence(
            mcp, key, token, 80, DELEGATED_CUSTOMER, policy_denial, trace=trace, step="child_refund_80"
        )
        first_refusal_epoch_ms = time.time_ns() // 1_000_000
        reject_refund_with_evidence(
            mcp, key, token, CHILD_LIMIT, OTHER_CUSTOMER, policy_denial, trace=trace, step="child_other_customer"
        )
        emit({"trace": trace, "first_refusal_epoch_ms": first_refusal_epoch_ms})
        trace = []
        receive(sys.stdin)
        reject_refund_with_evidence(
            mcp, key, token, CHILD_LIMIT, DELEGATED_CUSTOMER, "Chain revoked", trace=trace, step="child_revoked_retry"
        )
        emit({"trace": trace})
        return

    reject_refund(mcp, key, token, 80, DELEGATED_CUSTOMER, policy_denial, trace=trace, step="child_over_limit")
    if not show_mode:
        show(f"3/6  Refus · 80 € sur {DELEGATED_CUSTOMER}, plafond dépassé")
    reject_refund(mcp, key, token, CHILD_LIMIT, OTHER_CUSTOMER, policy_denial, trace=trace, step="child_other_customer")
    if not show_mode:
        show(f"4/6  Refus · {CHILD_LIMIT} € sur {OTHER_CUSTOMER}, client hors périmètre")

    view = check_limits(
        mcp, key, token, amount=CHILD_LIMIT, customer=DELEGATED_CUSTOMER,
        chain=1, caller=2, depth=1, trace=trace, step="child_limits",
    )
    refund(mcp, key, token, CHILD_LIMIT, DELEGATED_CUSTOMER, trace=trace, step="child_refund")
    if not show_mode:
        show(
            f"5/6  Mes limites · stoa_security, chaîne {view['budget']['chain_remaining']}, "
            f"racine {view['budget']['root_caller_remaining']}, profondeur {view['delegation_depth']} "
            f"avant remboursement de {CHILD_LIMIT} € accepté"
        )
    if trace is not None:
        emit({"trace": trace})
        trace = []
    else:
        emit({})

    receive(sys.stdin)
    reject_refund(mcp, key, token, CHILD_LIMIT, DELEGATED_CUSTOMER, "Chain revoked", trace=trace, step="child_revoked_retry")
    if not show_mode:
        show("6/6  Révocation · nouvel appel de l’enfant refusé")
    if trace is not None:
        emit({"trace": trace})


def orchestrate(mode: str = "") -> None:
    show_mode = mode == "show"
    preview_mode = mode == "preview"
    collected: list[dict] = []
    first_refusal_epoch_ms: int | None = None
    with agent_pair("/app/demo.py", mode) as (parent_agent, child_agent):
        send(parent_agent.stdin, receive(child_agent.stdout))
        for src, dst in (
            (parent_agent, child_agent),
            (child_agent, parent_agent),
            (parent_agent, child_agent),
        ):
            msg = receive(src.stdout)
            if show_mode or preview_mode:
                collected.extend(msg.pop("trace", []))
                if "first_refusal_epoch_ms" in msg:
                    first_refusal_epoch_ms = msg.pop("first_refusal_epoch_ms")
            send(dst.stdin, msg)
        if show_mode or preview_mode:
            collected.extend(receive(child_agent.stdout).get("trace", []))
    if show_mode:
        json.dump(collected, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        sys.stdout.flush()
    elif preview_mode:
        json.dump(
            {"steps": collected, "first_refusal_epoch_ms": first_refusal_epoch_ms},
            sys.stdout,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    mode_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        role_arg = sys.argv[1]
        if role_arg == "host":
            orchestrate(mode=mode_arg)
        else:
            _load_container_deps()
            {"parent": parent, "child": child}[role_arg](os.environ["STOA_GATEWAY_URL"], mode=mode_arg)
    except Exception:
        if mode_arg not in {"show", "preview"}:
            show("ÉCHEC · une étape de la démo MCP n’a pas abouti")
        sys.exit(1)
