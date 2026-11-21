"""Validate and render --show and --preview evidence for the refund demo."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

LIMITS = ("decision", "direct", "stoa_security", "local_inspection", "allowed", "local_inspection")
REFUND_OK = ("decision", "direct", "refunds_create", "admission_budget", "allowed", "ok")
EXEC_OK = ("execution", "direct", "refunds_create", "execution", "succeeded", "execution_succeeded")
DENIED = ("decision", "direct", "refunds_create", "argument_constraint", "denied", "argument_constraint_denied")
REVOKE = ("revocation", "revoke", None, "revocation", "changed", "revoked")
REVOKED = ("decision", "direct", "refunds_create", "chain_state", "denied", "chain_revoked")

# (step_id, label, expected_error_message, journal_signature, expects_execution_row)
CALLS = [
    ("bootstrap", "Parent bootstrap", None, None, False),
    ("parent_limits", "Parent limits", None, LIMITS, False),
    ("parent_over_limit", "Parent refund above limit", "Tool call rejected by role policy", DENIED, False),
    ("parent_refund", "Parent refund within limit", None, REFUND_OK, True),
    ("delegate", "Delegate to child", None, None, False),
    ("child_over_limit", "Child refund above limit", "Tool call rejected by role policy", DENIED, False),
    ("child_other_customer", "Child refund for another customer", "Tool call rejected by role policy", DENIED, False),
    ("child_limits", "Child limits", None, LIMITS, False),
    ("child_refund", "Child refund within limit", None, REFUND_OK, True),
    ("revoke", "Parent revoke", None, REVOKE, False),
    ("child_revoked_retry", "Child retry after revoke", "Chain revoked", REVOKED, False),
]

# (step_id, label, expected_error_message, expected_evidence, journal_signature, expects_execution_row, expects_client_id)
PREVIEW_CALLS = [
    ("bootstrap", "Parent bootstrap (no IdP, Ed25519 role)", None, None, None, False, False),
    ("delegate", "Delegate child token (cap 50 EUR, C-1042)", None, None, None, False, False),
    ("child_limits", "Child inspects limits (stoa_security)", None, None, LIMITS, False, False),
    ("child_refund_50", "refunds_create(50 EUR, C-1042)", None, None, REFUND_OK, True, True),
    (
        "child_refund_80",
        "refunds_create(80 EUR, C-1042)",
        "Tool call rejected by role policy",
        {"reason": "argument_constraint_denied", "constraint": "amount_exceeds_cap", "limit_eur": 50},
        DENIED,
        False,
        True,
    ),
    (
        "child_other_customer",
        "refunds_create(50 EUR, C-2077)",
        "Tool call rejected by role policy",
        {"reason": "argument_constraint_denied", "constraint": "customer_outside_scope"},
        DENIED,
        False,
        True,
    ),
    ("revoke", "Parent revokes delegation chain", None, None, REVOKE, False, False),
    (
        "child_revoked_retry",
        "refunds_create(50 EUR, C-1042) after revoke",
        "Chain revoked",
        {"reason": "chain_revoked"},
        REVOKED,
        False,
        True,
    ),
]


def strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def row_sig(row: dict) -> tuple:
    return tuple(row.get(k) for k in ("kind", "route", "tool", "rule", "result", "reason"))


def canonical_uuid(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError
    parsed = str(uuid.UUID(raw))
    if parsed != raw.lower():
        raise ValueError
    return parsed


def load_trace(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != len(CALLS):
        raise ValueError
    out = []
    for entry, (step, _, exp_err, _, _) in zip(data, CALLS):
        if not isinstance(entry, dict) or entry.get("step") != step:
            raise ValueError
        status = entry.get("http_status")
        if not strict_int(status) or not (100 <= status <= 599):
            raise ValueError
        item: dict = {"http_status": status}
        if exp_err is not None:
            msg = entry.get("error_message")
            if not isinstance(msg, str) or msg != exp_err:
                raise ValueError
            item["error_message"] = msg
            if "error_code" in entry:
                if not strict_int(entry["error_code"]):
                    raise ValueError
                item["error_code"] = entry["error_code"]
        elif "error_message" in entry or "error_code" in entry:
            raise ValueError
        out.append(item)
    return out


def load_journal(export_dir: Path) -> list[tuple[str, str]]:
    health = json.loads((export_dir / "decisions.health.json").read_text(encoding="utf-8"))
    if not isinstance(health, dict) or health.get("status") != "healthy" or health.get("gap_detected") is not False:
        raise ValueError
    lines = [ln for ln in (export_dir / "decisions.ndjson").read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    if len(rows) != 11 or not all(isinstance(r, dict) for r in rows):
        raise ValueError

    decisions: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    idx = 0
    for _, _, _, sig, has_exec in CALLS:
        if sig is None:
            continue
        row = rows[idx]
        idx += 1
        if row_sig(row) != sig:
            raise ValueError
        did = canonical_uuid(row.get("decision_id"))
        if did in seen_ids:
            raise ValueError
        seen_ids.add(did)
        decisions.append((did, row["reason"]))
        if has_exec:
            ex = rows[idx]
            idx += 1
            req_id = row.get("request_id")
            if (
                row_sig(ex) != EXEC_OK
                or canonical_uuid(ex.get("decision_id")) != did
                or not isinstance(req_id, str)
                or not req_id
                or ex.get("request_id") != req_id
            ):
                raise ValueError
    if idx != len(rows):
        raise ValueError
    return decisions


def load_preview_trace(path: Path) -> tuple[list[dict], int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError
    steps = raw.get("steps")
    first_refusal_ms = raw.get("first_refusal_epoch_ms")
    if not strict_int(first_refusal_ms) or first_refusal_ms <= 0:
        raise ValueError
    if not isinstance(steps, list) or len(steps) != len(PREVIEW_CALLS):
        raise ValueError
    out = []
    for entry, (step, _, exp_err, exp_ev, _, _, exp_cid) in zip(steps, PREVIEW_CALLS):
        if not isinstance(entry, dict) or entry.get("step") != step:
            raise ValueError
        status = entry.get("http_status")
        if not strict_int(status) or status != 200:
            raise ValueError
        item: dict = {"step": step, "http_status": status}
        if exp_cid:
            cid = canonical_uuid(entry.get("decision_id"))
            item["decision_id"] = cid
        elif "decision_id" in entry:
            raise ValueError
        if exp_err is not None:
            if entry.get("error_message") != exp_err or entry.get("error_code") != -32003:
                raise ValueError
            item["error_message"] = exp_err
            item["error_code"] = -32003
            ev = entry.get("evidence")
            if not isinstance(ev, dict):
                raise ValueError
            if canonical_uuid(ev.get("decision_id")) != item["decision_id"]:
                raise ValueError
            for k, v in (exp_ev or {}).items():
                if ev.get(k) != v:
                    raise ValueError
            item["evidence"] = ev
        else:
            if "error_message" in entry or "error_code" in entry or "evidence" in entry:
                raise ValueError
        out.append(item)
    return out, first_refusal_ms


def load_preview_journal(export_dir: Path, trace: list[dict]) -> tuple[list[tuple[str, str]], int, int]:
    health = json.loads((export_dir / "decisions.health.json").read_text(encoding="utf-8"))
    if not isinstance(health, dict) or health.get("status") != "healthy" or health.get("gap_detected") is not False:
        raise ValueError
    lines = [ln for ln in (export_dir / "decisions.ndjson").read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    if len(rows) != 7 or not all(isinstance(r, dict) for r in rows):
        raise ValueError

    decisions: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    correlated = 0
    idx = 0
    for entry, (_, _, _, _, sig, has_exec, exp_cid) in zip(trace, PREVIEW_CALLS):
        if sig is None:
            continue
        row = rows[idx]
        idx += 1
        if row_sig(row) != sig:
            raise ValueError
        did = canonical_uuid(row.get("decision_id"))
        if did in seen_ids:
            raise ValueError
        seen_ids.add(did)
        if exp_cid:
            if entry["decision_id"] != did:
                raise ValueError
            correlated += 1
        decisions.append((did, row["reason"]))
        if has_exec:
            ex = rows[idx]
            idx += 1
            req_id = row.get("request_id")
            if (
                row_sig(ex) != EXEC_OK
                or canonical_uuid(ex.get("decision_id")) != did
                or not isinstance(req_id, str)
                or not req_id
                or ex.get("request_id") != req_id
            ):
                raise ValueError
    if idx != len(rows) or correlated != 4:
        raise ValueError
    return decisions, len(rows), correlated


def render_preview(trace: list[dict], decisions: list[tuple[str, str]], row_count: int, correlated: int, caller_auth_seen: int) -> None:
    use_color = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"
    bold = "\033[1m" if use_color else ""
    dim = "\033[2m" if use_color else ""
    green = "\033[32m" if use_color else ""
    red = "\033[31m" if use_color else ""
    cyan = "\033[36m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    print(f"{bold}STOA — Agent Roles Preview{reset} {dim}(local, no IdP, simulated refunds){reset}\n")
    dec_iter = iter(decisions)
    for idx, (entry, (step, label, _, _, sig, _, exp_cid)) in enumerate(zip(trace, PREVIEW_CALLS), 1):
        if sig is None:
            badge = f"{cyan}SETUP  {reset}"
            detail = f"HTTP {entry['http_status']}"
        else:
            did, reason = next(dec_iter)
            if step == "child_refund_50":
                badge = f"{green}ALLOW  {reset}"
                detail = f"decision_id={did} (executed, journal matched)"
            elif step in {"child_refund_80", "child_other_customer", "child_revoked_retry"}:
                badge = f"{red}REFUSED{reset}"
                ev = entry["evidence"]
                extra = ""
                if ev.get("constraint") == "amount_exceeds_cap":
                    extra = f" · limit_eur={ev['limit_eur']}"
                elif ev.get("constraint"):
                    extra = f" · {ev['constraint']}"
                detail = f"decision_id={did} ({reason}{extra}, journal matched)"
            elif step == "revoke":
                badge = f"{cyan}REVOKE {reset}"
                detail = f"decision_id={did} ({reason})"
            else:
                badge = f"{green}ALLOW  {reset}"
                detail = f"decision_id={did} ({reason})"
            if exp_cid:
                assert entry["decision_id"] == did
        print(f"  {idx}/{len(PREVIEW_CALLS)}  {badge}  {label:<44} {detail}")

    print()
    print(f"  {green}Journal {reset} · {row_count} rows verified in decisions.ndjson (0 gaps, {correlated}/{correlated} client decision_id == journal)")
    print(f"  {green}Upstream{reset} · 1 simulated refund executed, 0 refused calls reached backend, caller_auth_headers_seen={caller_auth_seen}")


def main() -> int:
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "--preview" and sys.argv[4].isdigit():
            trace, first_refusal_ms = load_preview_trace(Path(sys.argv[2]))
            decisions, row_count, correlated = load_preview_journal(Path(sys.argv[3]), trace)
            caller_auth_seen = int(sys.argv[4])
            timing_file = os.environ.get("STOA_DEMO_TIMING_FILE")
            if timing_file:
                Path(timing_file).write_text(f"{first_refusal_ms}\n", encoding="utf-8")
            render_preview(trace, decisions, row_count, correlated, caller_auth_seen)
            return 0
        if len(sys.argv) != 4 or not sys.argv[3].isdigit():
            raise ValueError
        trace = load_trace(Path(sys.argv[1]))
        decisions = iter(load_journal(Path(sys.argv[2])))
        caller_auth_seen = int(sys.argv[3])
        print("STOA · Simulated refunds\n")
        for i, (entry, (_, label, _, sig, _)) in enumerate(zip(trace, CALLS), 1):
            parts = [f"HTTP {entry['http_status']}"]
            if "error_message" in entry:
                code = f" {entry['error_code']}" if "error_code" in entry else ""
                parts.append(f"JSON-RPC error{code}: {entry['error_message']}")
            if sig is None:
                parts.append("no journal decision")
            else:
                did, reason = next(decisions)
                parts.append(f"decision_id={did} ({reason})")
            print(f"{i:02d}/{len(CALLS)}  {label:<33} · {' | '.join(parts)}")
        print(f"\nUpstream mock · caller_auth_headers_seen={caller_auth_seen}")
        return 0
    except Exception:
        print("FAILED · unable to verify demo evidence", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
