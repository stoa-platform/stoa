"""Validate and render --show evidence for the refund demo."""

import json
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


def main() -> int:
    try:
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
