#!/usr/bin/env python3
"""Verify exported PoC observability v1 NDJSON journals, health sidecars, and optional stoactl CLI."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

VALID_KINDS = {"decision", "execution", "revocation", "journal_status"}
VALID_ROUTES = {"direct", "step", "fallback", "revoke", "ingress", "journal"}
VALID_RESULTS = {"allowed", "denied", "succeeded", "failed", "changed", "degraded"}
TOOL_ROUTES = {"direct", "step", "fallback"}
EXPECTED_EXPORT_FILES = {"decisions.ndjson", "decisions.health.json"}
MAX_HEALTH_BYTES = 4 * 1024
MAX_FILES = 64
ROTATION_HEALTH_KEYS = (
    "max_files",
    "active_generation",
    "retained_segments",
    "expired_segments",
    "retention_pruned",
)
HEALTH_BASE_REQUIRED_KEYS = {
    "schema_version",
    "status",
    "capacity_bytes",
    "bytes_used",
    "dropped_records",
    "gap_detected",
    "capacity_exceeded",
    "io_error",
    "updated_at",
}
HEALTH_ALL_ALLOWED_KEYS = (
    HEALTH_BASE_REQUIRED_KEYS | {"reason"} | set(ROTATION_HEALTH_KEYS)
)
KNOWN_REASONS = {
    "ok",
    "unauthorized",
    "invalid_request",
    "unsupported_method",
    "token_invalid",
    "dpop_invalid",
    "delegation_denied",
    "chain_revoked",
    "chain_inactive",
    "session_expired",
    "role_policy_denied",
    "policy_unavailable",
    "tool_not_found",
    "tool_denied",
    "argument_constraint_denied",
    "chain_budget_exceeded",
    "root_budget_exceeded",
    "admission_table_full",
    "revocation_table_full",
    "revoked",
    "execution_succeeded",
    "execution_failed",
    "backend_error",
    "journal_capacity_exceeded",
    "journal_io_error",
    "journal_corrupted",
    "journal_degraded",
    "local_inspection",
}

HEALTH_NEGATIVE_BOOL_FLAGS = {
    "degraded",
    "write_failed",
    "io_error",
    "corrupted",
    "dropped",
    "gap_detected",
    "capacity_exceeded",
}
HEALTH_POSITIVE_BOOL_FLAGS = {
    "writable",
    "ready",
    "ok",
    "healthy",
    "journal_writable",
    "key_ready",
    "enabled",
    "initialized",
}

# Sentinels / raw values that must never appear in exported reports or drafts.
RAW_SENTINELS = (
    "poc-parent-boot-",
    "poc-vault-key-",
    "refund-demo-backend-marker",
    "X-Stoa-Poc-Bootstrap-Secret",
    "Bearer ",
    "DPoP ",
    "eyJ",
    "acct-j3-1",
    "acct-fb",
    "acct-child-j3",
    "acct-revoked",
    "acct-race-",
    "acct-child-revoked",
    "C-1042",
    "C-2077",
    "pay_001",
    "sensitive-upstream-redirect-body",
    "agent-parent",
    "agent-child",
    "demo-parent",
    "demo-child",
)


def fail(msg: str) -> None:
    print(f"FAIL · {msg}", file=sys.stderr)
    sys.exit(1)


RFC3339_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$"
)


def parse_rfc3339_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    m = RFC3339_RE.fullmatch(raw.strip())
    if not m:
        return None
    base, frac, tz = m.groups()
    frac_norm = "." + frac[:6].ljust(6, "0") if frac is not None else ""
    tz_norm = "+00:00" if tz == "Z" else tz
    try:
        dt = datetime.fromisoformat(f"{base}{frac_norm}{tz_norm}")
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def is_real_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_export_dir(export_dir: Path, label: str) -> tuple[Path, Path]:
    try:
        dir_st = os.lstat(export_dir)
    except OSError:
        fail(f"{label}: export directory is missing or inaccessible")
    if not stat.S_ISDIR(dir_st.st_mode):
        fail(f"{label}: export path is not a regular directory")
    if dir_st.st_uid != os.geteuid() or (stat.S_IMODE(dir_st.st_mode) & 0o077) != 0:
        fail(f"{label}: export directory is not private (expected 0700 owned by current user)")

    entries = {p.name for p in export_dir.iterdir()}
    unexpected = entries - EXPECTED_EXPORT_FILES
    if unexpected:
        fail(f"{label}: unexpected file(s) in export directory (count={len(unexpected)})")
    missing = EXPECTED_EXPORT_FILES - entries
    if missing:
        fail(f"{label}: missing expected export file(s) (count={len(missing)})")

    journal = export_dir / "decisions.ndjson"
    health = export_dir / "decisions.health.json"
    for path in (journal, health):
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            fail(f"{label}: {path.name} is not a regular file")
        if stat.S_IMODE(st.st_mode) != 0o600:
            fail(f"{label}: {path.name} permissions must be 0600")
        if st.st_size == 0:
            fail(f"{label}: {path.name} is empty")
    return journal, health


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("duplicate key")
        obj[key] = val
    return obj


def load_health(
    health_path: Path,
    label: str,
    require_rotation: bool = False,
) -> dict[str, Any]:
    try:
        raw_bytes = health_path.read_bytes()
    except OSError:
        fail(f"{label}: invalid decisions.health.json")
    if not raw_bytes or len(raw_bytes) > MAX_HEALTH_BYTES:
        fail(f"{label}: decisions.health.json exceeds 4 KiB bound")
    try:
        data = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, ValueError):
        fail(f"{label}: invalid decisions.health.json")
    if not isinstance(data, dict):
        fail(f"{label}: decisions.health.json root must be a JSON object")

    if set(data.keys()) - HEALTH_ALL_ALLOWED_KEYS:
        fail(f"{label}: decisions.health.json contains unknown field")
    if not HEALTH_BASE_REQUIRED_KEYS.issubset(data.keys()):
        fail(f"{label}: decisions.health.json missing required field")
    if "reason" in data and data["reason"] is not None:
        if not isinstance(data["reason"], str) or data["reason"] not in KNOWN_REASONS:
            fail(f"{label}: decisions.health.json invalid or non-canonical reason")

    if not is_real_int(data.get("schema_version")) or data["schema_version"] != 1:
        fail(f"{label}: decisions.health.json invalid schema_version")
    if data.get("status") != "healthy":
        fail(f"{label}: decisions.health.json status is not healthy")

    if parse_rfc3339_utc(data.get("updated_at")) is None:
        fail(f"{label}: decisions.health.json invalid updated_at")

    for int_key in ("capacity_bytes", "bytes_used"):
        val = data.get(int_key)
        if not is_real_int(val) or val < 0:
            fail(f"{label}: decisions.health.json invalid {int_key}")
    if not is_real_int(data.get("dropped_records")) or data["dropped_records"] != 0:
        fail(f"{label}: decisions.health.json reports non-zero or invalid dropped_records")
    for required_false in ("gap_detected", "capacity_exceeded", "io_error"):
        if data.get(required_false) is not False:
            fail(f"{label}: decisions.health.json {required_false} must be false")

    present_rot = [k for k in ROTATION_HEALTH_KEYS if k in data]
    if present_rot and len(present_rot) != len(ROTATION_HEALTH_KEYS):
        fail(f"{label}: decisions.health.json has incomplete rotation fields")

    if present_rot:
        max_files = data["max_files"]
        active_gen = data["active_generation"]
        retained = data["retained_segments"]
        expired = data["expired_segments"]
        pruned = data["retention_pruned"]
        if not is_real_int(max_files) or max_files < 1 or max_files > MAX_FILES:
            fail(f"{label}: decisions.health.json invalid max_files")
        if not is_real_int(active_gen) or active_gen < 0:
            fail(f"{label}: decisions.health.json invalid active_generation")
        if not is_real_int(retained) or retained < 1 or retained > max_files:
            fail(f"{label}: decisions.health.json invalid retained_segments")
        if not is_real_int(expired) or expired < 0:
            fail(f"{label}: decisions.health.json invalid expired_segments")
        if not isinstance(pruned, bool) or pruned != (expired > 0):
            fail(f"{label}: decisions.health.json invalid retention_pruned")
        if active_gen + 1 != expired + retained:
            fail(f"{label}: decisions.health.json generation and segment counts mismatch")

    if require_rotation:
        if not present_rot:
            fail(f"{label}: rotation proof requires rotation metadata in decisions.health.json")
        if data["active_generation"] < 1 or data["retained_segments"] < 2:
            fail(
                f"{label}: rotation proof expected multiple generations "
                f"(active_generation>=1, retained_segments>=2)"
            )
        if data["expired_segments"] != 0 or data["retention_pruned"] is not False:
            fail(f"{label}: rotation proof must not trigger planned retention expiry")

    return data


def load_ndjson(journal_path: Path, label: str) -> list[dict[str, Any]]:
    try:
        raw_text = journal_path.read_text(encoding="utf-8")
    except OSError:
        fail(f"{label}: unable to read decisions.ndjson")

    lines = raw_text.splitlines()
    if not lines:
        fail(f"{label}: decisions.ndjson has 0 lines")

    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            fail(f"{label}: malformed blank line at line {idx}")
        try:
            obj = json.loads(line)
        except ValueError:
            fail(f"{label}: malformed JSON at line {idx}")
        if not isinstance(obj, dict):
            fail(f"{label}: line {idx} is not a JSON object")
        validate_common_event(obj, idx, label)
        events.append(obj)
    return events


def validate_common_event(ev: dict[str, Any], line_no: int, label: str) -> None:
    if not is_real_int(ev.get("schema_version")) or ev["schema_version"] != 1:
        fail(f"{label}: line {line_no} invalid schema_version")

    kind = ev.get("kind")
    if kind not in VALID_KINDS:
        fail(f"{label}: line {line_no} invalid kind")

    route = ev.get("route")
    if route not in VALID_ROUTES:
        fail(f"{label}: line {line_no} invalid route")

    result = ev.get("result")
    if result not in VALID_RESULTS:
        fail(f"{label}: line {line_no} invalid result")

    reason = ev.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        fail(f"{label}: line {line_no} missing or empty stable reason")

    if kind == "journal_status" and result == "degraded":
        fail(f"{label}: line {line_no} journal_status reported degraded")

    for bal_key in ("chain_remaining", "root_remaining"):
        val = ev.get(bal_key)
        if val is not None:
            if not is_real_int(val) or val < 0:
                fail(f"{label}: line {line_no} invalid remaining balance")

    for key, val in ev.items():
        if key != "schema_version" and (key.endswith("_version") or key == "version"):
            if val is not None and (not is_real_int(val) or val <= 0):
                fail(f"{label}: line {line_no} non-positive version field")


def check_positive_versions(decisions: list[dict[str, Any]], label: str) -> None:
    version_keys = ("policy_version", "role_version", "artifact_version", "version")
    allowed = [d for d in decisions if d["result"] == "allowed"]
    for idx, d in enumerate(allowed, start=1):
        found_positive = any(
            is_real_int(d.get(k)) and d[k] > 0 for k in version_keys
        )
        if not found_positive:
            fail(f"{label}: allowed decision #{idx} missing positive version field")


def check_decision_execution_parity(
    allowed_decisions: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    label: str,
) -> None:
    by_id: dict[str, dict[str, Any]] = {}
    for d in allowed_decisions:
        did = d.get("decision_id")
        if not isinstance(did, str) or not did.strip():
            fail(f"{label}: allowed decision missing decision_id")
        if did in by_id:
            fail(f"{label}: duplicate decision_id among allowed decisions")
        by_id[did] = d

    exec_ids: set[str] = set()
    for ex in executions:
        did = ex.get("decision_id")
        rid = ex.get("request_id")
        if not isinstance(did, str) or not did.strip():
            fail(f"{label}: execution missing decision_id")
        if not isinstance(rid, str) or not rid.strip():
            fail(f"{label}: execution missing request_id")
        if did in exec_ids:
            fail(f"{label}: duplicate execution for same decision_id")
        if did not in by_id:
            fail(f"{label}: execution decision_id does not match any allowed tool decision")
        dec = by_id[did]
        if dec.get("request_id") != rid:
            fail(f"{label}: execution request_id mismatch with decision")
        if dec.get("tool") != ex.get("tool"):
            fail(f"{label}: execution tool mismatch with decision")
        if dec.get("step_index") != ex.get("step_index"):
            fail(f"{label}: execution step_index mismatch with decision")
        exec_ids.add(did)

    if exec_ids != set(by_id.keys()):
        fail(
            f"{label}: decision/execution ID mismatch "
            f"(allowed={len(by_id)}, executions={len(exec_ids)})"
        )


def check_unique_decision_ids(events: list[dict[str, Any]], label: str) -> None:
    seen: set[str] = set()
    for ev in events:
        if ev["kind"] != "decision":
            continue
        did = ev.get("decision_id")
        if ev["route"] in TOOL_ROUTES:
            if not isinstance(did, str) or not did.strip():
                fail(f"{label}: tool decision missing decision_id")
        if did is not None:
            if not isinstance(did, str) or not did.strip():
                fail(f"{label}: invalid decision_id")
            if did in seen:
                fail(f"{label}: decision_id collision detected")
            seen.add(did)


def verify_jalon3(
    export_dir: Path,
    require_rotation: bool = False,
) -> tuple[Path, list[dict[str, Any]], str]:
    label = "Jalon3"
    journal_path, health_path = check_export_dir(export_dir, label)
    load_health(health_path, label, require_rotation=require_rotation)
    events = load_ndjson(journal_path, label)

    check_unique_decision_ids(events, label)

    tool_decisions = [
        ev for ev in events if ev["kind"] == "decision" and ev["route"] in TOOL_ROUTES
    ]
    ingress_decisions = [
        ev for ev in events if ev["kind"] == "decision" and ev["route"] == "ingress"
    ]
    executions = [ev for ev in events if ev["kind"] == "execution"]
    revocations = [ev for ev in events if ev["kind"] == "revocation"]

    # Zero internal filter events and no local_inspection in J3.
    expected_j3_tools = {"payments_list", "payments_fail", "payments_hidden"}
    if any(ev.get("tool") not in expected_j3_tools for ev in tool_decisions):
        fail(f"{label}: unexpected tool recorded in J3 decisions")
    if any(ev.get("reason") == "local_inspection" for ev in tool_decisions):
        fail(f"{label}: unexpected local_inspection event in J3")

    hidden_decisions = [ev for ev in tool_decisions if ev.get("tool") == "payments_hidden"]
    if len(hidden_decisions) != 2:
        fail(
            f"{label}: expected exact 2 payments_hidden decisions "
            f"(0 from tools/list filter), got {len(hidden_decisions)}"
        )

    allowed = [ev for ev in tool_decisions if ev["result"] == "allowed"]
    denied = [ev for ev in tool_decisions if ev["result"] == "denied"]
    if len(tool_decisions) != 42 or len(allowed) != 13 or len(denied) != 29:
        fail(
            f"{label}: expected 42 tool decisions (13 allowed, 29 denied), "
            f"got {len(tool_decisions)} ({len(allowed)} allowed, {len(denied)} denied)"
        )

    expected_denied_reasons = Counter({
        "role_policy_denied": 2,
        "argument_constraint_denied": 1,
        "chain_revoked": 2,
        "root_budget_exceeded": 13,
        "chain_budget_exceeded": 11,
    })
    actual_denied_reasons = Counter(ev["reason"] for ev in denied)
    if actual_denied_reasons != expected_denied_reasons:
        fail(f"{label}: denied decision reasons mismatch expected counts")

    exec_ok = [ev for ev in executions if ev["result"] == "succeeded"]
    exec_fail = [ev for ev in executions if ev["result"] == "failed"]
    if len(executions) != 13 or len(exec_ok) != 11 or len(exec_fail) != 2:
        fail(
            f"{label}: expected 13 executions (11 succeeded, 2 failed), "
            f"got {len(executions)} ({len(exec_ok)} succeeded, {len(exec_fail)} failed)"
        )
    if not all(ev["reason"] == "execution_succeeded" for ev in exec_ok):
        fail(f"{label}: succeeded execution missing reason execution_succeeded")
    if not all(ev["reason"] == "backend_error" for ev in exec_fail):
        fail(f"{label}: failed execution missing reason backend_error")

    if len(revocations) != 1:
        fail(f"{label}: expected 1 revocation mutation, got {len(revocations)}")
    if revocations[0]["route"] != "revoke" or revocations[0]["result"] != "changed":
        fail(f"{label}: revocation event route/result mismatch")

    for ev in ingress_decisions:
        if ev["result"] != "denied":
            fail(f"{label}: unexpected non-denied ingress decision")

    check_positive_versions(tool_decisions, label)
    check_decision_execution_parity(allowed, executions, label)

    # Verify the 2 fallbacks: 1 allowed, 1 denied (argument_constraint_denied),
    # same request_id + step_index as primary step, distinct decision_id.
    fallbacks = [ev for ev in tool_decisions if ev["route"] == "fallback"]
    fb_allowed = [ev for ev in fallbacks if ev["result"] == "allowed"]
    fb_denied = [ev for ev in fallbacks if ev["result"] == "denied"]
    if len(fallbacks) != 2 or len(fb_allowed) != 1 or len(fb_denied) != 1:
        fail(
            f"{label}: expected 2 fallbacks (1 allowed, 1 denied), "
            f"got {len(fallbacks)} ({len(fb_allowed)} allowed, {len(fb_denied)} denied)"
        )
    if fb_denied[0]["reason"] != "argument_constraint_denied":
        fail(f"{label}: denied fallback missing reason argument_constraint_denied")

    exec_by_did = {ev["decision_id"]: ev for ev in executions}
    step_decisions = [ev for ev in tool_decisions if ev["route"] == "step"]
    for fb in fallbacks:
        rid = fb.get("request_id")
        sidx = fb.get("step_index")
        if not isinstance(rid, str) or not rid.strip() or not is_real_int(sidx):
            fail(f"{label}: fallback decision missing request_id or integer step_index")
        primaries = [
            p
            for p in step_decisions
            if p.get("request_id") == rid and p.get("step_index") == sidx
        ]
        if len(primaries) != 1:
            fail(
                f"{label}: fallback expected 1 primary step with matching "
                f"request_id/step_index, got {len(primaries)}"
            )
        primary = primaries[0]
        if primary["decision_id"] == fb["decision_id"]:
            fail(f"{label}: fallback decision_id must differ from primary decision_id")
        if primary["result"] != "allowed":
            fail(f"{label}: fallback primary decision expected allowed")
        primary_exec = exec_by_did.get(primary["decision_id"])
        if (
            primary_exec is None
            or primary_exec["result"] != "failed"
            or primary_exec["reason"] != "backend_error"
        ):
            fail(f"{label}: fallback primary execution expected failed with backend_error")

    # Verify exact balances for all admitted calls, especially concurrent root-limit group (Chain B).
    revoke_idx = next(i for i, ev in enumerate(events) if ev["kind"] == "revocation")
    pre_allowed = [
        ev
        for i, ev in enumerate(events)
        if i < revoke_idx
        and ev["kind"] == "decision"
        and ev["route"] in TOOL_ROUTES
        and ev["result"] == "allowed"
    ]
    post_allowed = [
        ev
        for i, ev in enumerate(events)
        if i > revoke_idx
        and ev["kind"] == "decision"
        and ev["route"] in TOOL_ROUTES
        and ev["result"] == "allowed"
    ]
    if len(pre_allowed) != 5 or len(post_allowed) != 8:
        fail(
            f"{label}: expected 5 allowed decisions before revocation and 8 after, "
            f"got {len(pre_allowed)} before / {len(post_allowed)} after"
        )

    for ev in allowed:
        cr = ev.get("chain_remaining")
        rr = ev.get("root_remaining")
        if not is_real_int(cr) or not is_real_int(rr) or cr < 0 or rr < 0:
            fail(f"{label}: allowed decision has missing or negative remaining balances")

    chain_b = [ev for ev in post_allowed if ev["chain_remaining"] - ev["root_remaining"] == 2]
    chain_c = [ev for ev in post_allowed if ev["root_remaining"] - ev["chain_remaining"] == 3]
    if len(chain_b) != 3 or len(chain_c) != 5:
        fail(
            f"{label}: unexpected post-revocation concurrent budget groups "
            f"(root-limit={len(chain_b)}, chain-limit={len(chain_c)})"
        )

    actual_b = Counter((ev["chain_remaining"], ev["root_remaining"]) for ev in chain_b)
    expected_b = Counter([(4, 2), (3, 1), (2, 0)])
    if actual_b != expected_b:
        fail(f"{label}: concurrent root-limit receipts mismatch")

    actual_c = Counter((ev["chain_remaining"], ev["root_remaining"]) for ev in chain_c)
    expected_c = Counter([(4, 7), (3, 6), (2, 5), (1, 4), (0, 3)])
    if actual_c != expected_c:
        fail(f"{label}: concurrent chain-limit receipts mismatch")

    actual_a = Counter((ev["chain_remaining"], ev["root_remaining"]) for ev in pre_allowed)
    if actual_a != expected_c:
        fail(f"{label}: pre-revocation chain A receipts mismatch")

    b_chains = {ev.get("chain_id") for ev in chain_b if ev.get("chain_id") is not None}
    c_chains = {ev.get("chain_id") for ev in chain_c if ev.get("chain_id") is not None}
    if b_chains and len(b_chains) != 1:
        fail(f"{label}: concurrent root-limit group spanned multiple chain_ids")
    if c_chains and len(c_chains) != 1:
        fail(f"{label}: concurrent chain-limit group spanned multiple chain_ids")
    if b_chains and c_chains and b_chains == c_chains:
        fail(f"{label}: concurrent root-limit and chain-limit groups shared the same chain_id")

    summary = (
        f"J3           · PASS · 42 décisions (13 admises, 29 refusées), "
        f"13 exécutions (11 succès, 2 échecs), 2 replis (1 admis, 1 refusé), "
        f"1 révocation, soldes concurrents exacts, continuité post-restart OK"
        + (f" (+{len(ingress_decisions)} ingress)" if ingress_decisions else "")
    )
    return journal_path, events, summary


def verify_demo(export_dir: Path) -> str:
    label = "Demo"
    journal_path, health_path = check_export_dir(export_dir, label)
    load_health(health_path, label)
    events = load_ndjson(journal_path, label)

    check_unique_decision_ids(events, label)

    tool_decisions = [
        ev for ev in events if ev["kind"] == "decision" and ev["route"] in TOOL_ROUTES
    ]
    executions = [ev for ev in events if ev["kind"] == "execution"]
    revocations = [ev for ev in events if ev["kind"] == "revocation"]

    security_decisions = [ev for ev in tool_decisions if ev.get("tool") == "stoa_security"]
    refund_decisions = [ev for ev in tool_decisions if ev.get("tool") == "refunds_create"]
    other_decisions = [
        ev
        for ev in tool_decisions
        if ev.get("tool") not in {"stoa_security", "refunds_create"}
    ]
    if other_decisions:
        fail(f"{label}: unexpected tool decisions recorded (count={len(other_decisions)})")

    if security_decisions:
        if len(security_decisions) != 2:
            fail(f"{label}: expected 2 explicit stoa_security inspections, got {len(security_decisions)}")
        if not all(
            ev["result"] == "allowed" and ev["reason"] == "local_inspection"
            for ev in security_decisions
        ):
            fail(f"{label}: stoa_security inspection must be allowed with reason local_inspection")

    refund_allowed = [ev for ev in refund_decisions if ev["result"] == "allowed"]
    refund_denied = [ev for ev in refund_decisions if ev["result"] == "denied"]
    if len(refund_decisions) != 6 or len(refund_allowed) != 2 or len(refund_denied) != 4:
        fail(
            f"{label}: expected 6 refunds_create decisions (2 allowed, 4 denied), "
            f"got {len(refund_decisions)} ({len(refund_allowed)} allowed, {len(refund_denied)} denied)"
        )

    expected_denied_reasons = Counter({
        "argument_constraint_denied": 3,
        "chain_revoked": 1,
    })
    actual_denied_reasons = Counter(ev["reason"] for ev in refund_denied)
    if actual_denied_reasons != expected_denied_reasons:
        fail(f"{label}: denied refunds_create reasons mismatch expected counts")

    if len(executions) != 2 or not all(
        ev["result"] == "succeeded"
        and ev["reason"] == "execution_succeeded"
        and ev.get("tool") == "refunds_create"
        for ev in executions
    ):
        fail(f"{label}: expected 2 succeeded refunds_create executions, got {len(executions)}")

    if len(revocations) != 1 or revocations[0]["route"] != "revoke" or revocations[0]["result"] != "changed":
        fail(f"{label}: expected 1 revocation mutation (route=revoke, result=changed), got {len(revocations)}")

    rev_denied_ev = next(ev for ev in refund_denied if ev["reason"] == "chain_revoked")
    revoke_idx = next(i for i, ev in enumerate(events) if ev["kind"] == "revocation")
    rev_denied_idx = next(i for i, ev in enumerate(events) if ev is rev_denied_ev)
    if rev_denied_idx <= revoke_idx:
        fail(f"{label}: revocation denial occurred before revocation mutation")

    check_positive_versions(refund_decisions, label)
    check_decision_execution_parity(refund_allowed, executions, label)

    balances = [(ev.get("chain_remaining"), ev.get("root_remaining")) for ev in refund_allowed]
    if balances != [(1, 2), (0, 1)]:
        fail(f"{label}: allowed refund remaining balances mismatch")

    sec_note = (
        f", {len(security_decisions)} inspections stoa_security"
        if security_decisions
        else ", 0 inspection stoa_security enregistrée"
    )
    return (
        f"Démo         · PASS · 6 décisions refunds_create (2 admises, 4 refusées : 3 contraintes, 1 révocation), "
        f"2 résultats, 1 révocation{sec_note}"
    )


def parse_event_time(ev: dict[str, Any]) -> datetime | None:
    for key in ("ts", "timestamp", "occurred_at", "created_at", "at"):
        val = ev.get(key)
        if isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def compute_time_window(events: list[dict[str, Any]]) -> tuple[str, str]:
    times = [t for ev in events if (t := parse_event_time(ev)) is not None]
    if times:
        start = min(times) - timedelta(seconds=60)
        end = max(times) + timedelta(seconds=60)
    else:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def check_no_sentinels(text: str, context: str) -> None:
    sentinels = list(RAW_SENTINELS)
    for env_key in ("STOA_POC_BOOTSTRAP_SECRET", "STOA_POC_UPSTREAM_API_KEY"):
        env_val = os.environ.get(env_key, "")
        if env_val:
            sentinels.append(env_val)
    for sentinel in sentinels:
        if sentinel in text:
            fail(f"CLI ({context}): raw/sentinel data leaked into output")


def verify_stoactl(
    stoactl_bin: str,
    journal_path: Path,
    events: list[dict[str, Any]],
    draft_dir: Path,
    require_rotation: bool = False,
) -> str:
    bin_path = Path(stoactl_bin)
    if not bin_path.is_absolute():
        fail("CLI: STOA_POC_STOACTL_BIN must be an absolute path")
    if not bin_path.is_file() or not os.access(bin_path, os.X_OK):
        fail("CLI: STOA_POC_STOACTL_BIN is not an executable file")

    try:
        draft_st = os.lstat(draft_dir)
    except OSError:
        fail("CLI: draft directory is missing or inaccessible")
    if not stat.S_ISDIR(draft_st.st_mode):
        fail("CLI: draft path must be a non-symlink directory")
    if draft_st.st_uid != os.geteuid() or (stat.S_IMODE(draft_st.st_mode) & 0o077) != 0:
        fail("CLI: draft directory must be private (0700)")

    from_ts, to_ts = compute_time_window(events)
    report_cmd = [
        str(bin_path),
        "-o",
        "json",
        "decisions",
        "report",
        "--journal",
        str(journal_path),
        "--from",
        from_ts,
        "--to",
        to_ts,
    ]
    report_proc = subprocess.run(
        report_cmd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if report_proc.returncode != 0:
        fail(f"CLI: stoactl decisions report exited with {report_proc.returncode}")

    report_raw = report_proc.stdout
    try:
        report_obj = json.loads(report_raw)
    except ValueError:
        fail("CLI: stoactl decisions report did not return valid JSON")
    check_no_sentinels(report_raw, "report")

    journal_meta = report_obj.get("journal") if isinstance(report_obj, dict) else None
    if not isinstance(journal_meta, dict):
        fail("CLI: stoactl decisions report missing journal health object")
    if journal_meta.get("availability") != "healthy" or journal_meta.get("gap_detected") is not False:
        fail("CLI: stoactl decisions report did not report healthy gap-free journal")
    if journal_meta.get("expired_segments") != 0 or journal_meta.get("retention_pruned") is not False:
        fail("CLI: stoactl decisions report reported unexpected retention expiry")
    if require_rotation:
        active_gen = journal_meta.get("active_generation")
        retained_segs = journal_meta.get("retained_segments")
        if not is_real_int(active_gen) or active_gen < 1 or not is_real_int(retained_segs) or retained_segs < 2:
            fail("CLI: stoactl decisions report did not reflect multi-generation rotation")

    target_decision = next(
        (
            ev["decision_id"]
            for ev in events
            if ev["kind"] == "decision" and ev["route"] in TOOL_ROUTES and ev["result"] == "denied"
        ),
        None,
    )
    if not target_decision:
        fail("CLI: unable to find a denied decision_id for mark-unexpected")

    mark_cmd = [
        str(bin_path),
        "-o",
        "json",
        "decisions",
        "mark-unexpected",
        target_decision,
        "--journal",
        str(journal_path),
        "--draft-dir",
        str(draft_dir),
    ]
    for attempt in (1, 2):
        mark_proc = subprocess.run(
            mark_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if mark_proc.returncode != 0:
            fail(f"CLI: stoactl decisions mark-unexpected (run {attempt}/2) exited with {mark_proc.returncode}")
        check_no_sentinels(mark_proc.stdout, f"mark-unexpected#{attempt}")

    draft_files = [p for p in draft_dir.iterdir() if not p.name.startswith(".")]
    if len(draft_files) != 1:
        fail(f"CLI: expected exact 1 draft file after 2 mark-unexpected runs, got {len(draft_files)}")
    draft_st_file = os.lstat(draft_files[0])
    if not stat.S_ISREG(draft_st_file.st_mode):
        fail("CLI: draft entry is not a regular file")
    check_no_sentinels(draft_files[0].read_text(encoding="utf-8", errors="replace"), "draft")

    return "CLI stoactl  · PASS · report JSON sans sentinelle/brut, mark-unexpected idempotent (1 fichier brouillon)"


def main() -> None:
    require_rotation = False
    pos_args: list[str] = []
    for arg in sys.argv[1:]:
        if arg == "--require-rotation":
            require_rotation = True
        else:
            pos_args.append(arg)

    if len(pos_args) < 2 or len(pos_args) > 4:
        print(
            "Usage: verify_observability.py [--require-rotation] <j3-export-dir> <demo-export-dir> [stoactl-bin] [draft-dir]",
            file=sys.stderr,
        )
        sys.exit(2)

    j3_dir = Path(pos_args[0])
    demo_dir = Path(pos_args[1])
    stoactl_bin = pos_args[2] if len(pos_args) >= 3 else ""
    draft_dir = Path(pos_args[3]) if len(pos_args) == 4 else None

    j3_journal, j3_events, j3_summary = verify_jalon3(
        j3_dir, require_rotation=require_rotation
    )
    demo_summary = verify_demo(demo_dir)

    print(j3_summary)
    print(demo_summary)
    if require_rotation:
        print("Rotation     · PASS · générations multiples exportées sans expiration ni perte")

    if stoactl_bin:
        if draft_dir is None:
            fail("CLI: draft-dir argument required when STOA_POC_STOACTL_BIN is set")
        cli_summary = verify_stoactl(
            stoactl_bin,
            j3_journal,
            j3_events,
            draft_dir,
            require_rotation=require_rotation,
        )
        print(cli_summary)
    else:
        print("CLI stoactl  · NON INCLUSE (STOA_POC_STOACTL_BIN non fourni)")


if __name__ == "__main__":
    main()
