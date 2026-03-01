#!/usr/bin/env python3
"""heg-state — HEGEMON Agent State Store CLI.

Centralized SQLite WAL state tracking for parallel Claude Code sessions.
Replaces .claude/claims/*.json with queryable, concurrent-safe SQL.

Usage:
    heg-state start  --ticket CAB-1350 --role backend --branch feat/...
    heg-state step   CAB-1350 pr-created --pr 578
    heg-state done   CAB-1350
    heg-state ls     [--project stoa] [--mine]
    heg-state history CAB-1350
    heg-state claim  CAB-1350 [--phase 1 --mega CAB-1290 --tickets T1,T2]
    heg-state release CAB-1350 [--phase 1]
    heg-state claims [MEGA-ID]
    heg-state cleanup --stale 2h
    heg-state brief  [--project stoa]
    heg-state ticket-upsert CAB-1350 --title "..." --status InProgress [--estimate 5] [--component gateway]
    heg-state ticket-ls [--cycle current] [--status InProgress] [--component gateway]
    heg-state ticket-sync --from-remote
    heg-state council-cache CAB-1350 --score 8.5 --verdict Go --hash abc123
    heg-state council-check CAB-1350 --hash abc123
    heg-state queue add CAB-1550 CAB-1551 --priority 1
    heg-state queue ls [--all]
    heg-state queue next --role backend [--format json]
    heg-state queue dispatch <job_id> <worker>
    heg-state queue done <job_id>
    heg-state queue fail <job_id> "reason"
    heg-state queue cancel <job_id>
    heg-state queue flush
    heg-state queue stats
    heg-state queue current
"""

import argparse
import json
import os
import platform
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("HEGEMON_STATE_DB", Path.home() / ".hegemon" / "state.db"))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

VALID_STEPS = [
    "claimed", "coding", "pr-created", "ci-green", "ci-failed",
    "merging", "merged", "cd-verified", "blocked", "paused", "done",
]
VALID_ROLES = ["interactive", "backend", "frontend", "auth", "mcp", "qa"]
VALID_SOURCES = ["local", "ci-l1", "ci-l3", "ci-l3.5"]

# ── Remote sync (PocketBase) ─────────────────────────────────────

REMOTE_URL = os.environ.get("HEGEMON_REMOTE_URL")  # e.g., https://state.gostoa.dev
REMOTE_EMAIL = os.environ.get("HEGEMON_REMOTE_EMAIL", "admin@gostoa.dev")
REMOTE_PASSWORD = os.environ.get("HEGEMON_REMOTE_PASSWORD")
TOKEN_CACHE_FILE = Path.home() / ".hegemon" / ".pb_token"

_token_cache: dict = {"token": None, "expires": 0.0}


def _remote_enabled() -> bool:
    return bool(REMOTE_URL and REMOTE_PASSWORD)


def _remote_auth() -> str | None:
    """Get PocketBase admin auth token. Cached in memory + file."""
    if not _remote_enabled():
        return None

    # Memory cache
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]

    # File cache (for cross-process reuse by hooks)
    if TOKEN_CACHE_FILE.exists():
        try:
            cached = json.loads(TOKEN_CACHE_FILE.read_text())
            if cached.get("expires", 0) > time.time():
                _token_cache["token"] = cached["token"]
                _token_cache["expires"] = cached["expires"]
                return cached["token"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Fresh auth
    try:
        data = json.dumps({"identity": REMOTE_EMAIL, "password": REMOTE_PASSWORD}).encode()
        req = urllib.request.Request(
            f"{REMOTE_URL}/api/admins/auth-with-password",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read())
        token = result["token"]
        expires = time.time() + 7200  # 2h (PB admin tokens last 14d, but refresh often)

        _token_cache["token"] = token
        _token_cache["expires"] = expires

        # Persist for hooks
        TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_FILE.write_text(json.dumps({"token": token, "expires": expires}))

        return token
    except Exception:
        return None


def _remote_push(collection: str, data: dict) -> None:
    """Create a record in PocketBase. Best-effort."""
    token = _remote_auth()
    if not token:
        return
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{REMOTE_URL}/api/collections/{collection}/records",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": token},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # best-effort, SQLite is primary


def _remote_upsert(collection: str, filter_field: str, filter_value: str, data: dict) -> None:
    """Upsert: find by filter field, update or create."""
    token = _remote_auth()
    if not token:
        return
    try:
        encoded_filter = urllib.parse.quote(f'{filter_field}="{filter_value}"')
        req = urllib.request.Request(
            f"{REMOTE_URL}/api/collections/{collection}/records?filter={encoded_filter}&perPage=1",
            headers={"Authorization": token},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read())

        if result.get("totalItems", 0) > 0:
            pb_id = result["items"][0]["id"]
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{REMOTE_URL}/api/collections/{collection}/records/{pb_id}",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": token},
                method="PATCH",
            )
            urllib.request.urlopen(req, timeout=5)
        else:
            _remote_push(collection, data)
    except Exception:
        pass


def _remote_delete(collection: str, filter_field: str, filter_value: str) -> None:
    """Delete a record by filter. Best-effort."""
    token = _remote_auth()
    if not token:
        return
    try:
        encoded_filter = urllib.parse.quote(f'{filter_field}="{filter_value}"')
        req = urllib.request.Request(
            f"{REMOTE_URL}/api/collections/{collection}/records?filter={encoded_filter}&perPage=1",
            headers={"Authorization": token},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read())

        if result.get("totalItems", 0) > 0:
            pb_id = result["items"][0]["id"]
            req = urllib.request.Request(
                f"{REMOTE_URL}/api/collections/{collection}/records/{pb_id}",
                headers={"Authorization": token},
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hostname() -> str:
    return platform.node()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    # Always run schema — all statements use IF NOT EXISTS so this is
    # idempotent and handles migrations (new tables added to schema.sql).
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


# ── Session commands ──────────────────────────────────────────────


def cmd_start(args: argparse.Namespace) -> None:
    instance_id = args.instance or f"t{int(time.time()) % 100000}-{os.urandom(2).hex()}"
    now = _now()
    project = args.project or os.environ.get("HEGEMON_PROJECT", "stoa")
    role = args.role or os.environ.get("STOA_INSTANCE", "interactive")

    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (instance_id, project, role, ticket, branch, step, pr, host, source, pid, started_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'claimed', NULL, ?, ?, ?, ?, ?)""",
        (instance_id, project, role, args.ticket, args.branch,
         _hostname(), args.source or "local", os.getpid(), now, now),
    )
    # Milestone
    if args.ticket:
        conn.execute(
            "INSERT INTO milestones (ticket, step, instance_id, project, created_at) VALUES (?, 'claimed', ?, ?, ?)",
            (args.ticket, instance_id, project, now),
        )
    conn.commit()
    conn.close()
    print(f"Session started: {instance_id} → {args.ticket or '(no ticket)'}")

    # Remote sync
    _remote_upsert("sessions", "instance_id", instance_id, {
        "instance_id": instance_id, "project": project, "role": role,
        "ticket": args.ticket or "", "branch": args.branch or "",
        "step": "claimed", "host": _hostname(), "source": args.source or "local",
        "pid": os.getpid(), "started_at": now, "updated_at": now,
    })
    if args.ticket:
        _remote_push("milestones", {
            "ticket": args.ticket, "step": "claimed",
            "instance_id": instance_id, "project": project, "event_at": now,
        })


def cmd_step(args: argparse.Namespace) -> None:
    if args.step not in VALID_STEPS:
        print(f"Invalid step '{args.step}'. Valid: {', '.join(VALID_STEPS)}", file=sys.stderr)
        sys.exit(1)

    now = _now()
    conn = _connect()

    # Update session
    updated = conn.execute(
        "UPDATE sessions SET step=?, pr=COALESCE(?, pr), updated_at=? WHERE ticket=?",
        (args.step, args.pr, now, args.ticket),
    ).rowcount

    if updated == 0:
        print(f"No active session for ticket {args.ticket}", file=sys.stderr)
        sys.exit(1)

    # Fetch instance_id and project for milestone
    row = conn.execute(
        "SELECT instance_id, project FROM sessions WHERE ticket=?", (args.ticket,)
    ).fetchone()

    conn.execute(
        "INSERT INTO milestones (ticket, step, instance_id, project, pr, sha, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (args.ticket, args.step, row["instance_id"], row["project"],
         args.pr, args.sha, args.detail, now),
    )

    # Auto-transition: done → clean up session
    if args.step == "done":
        conn.execute("DELETE FROM sessions WHERE ticket=?", (args.ticket,))

    conn.commit()
    conn.close()
    pr_info = f" (PR #{args.pr})" if args.pr else ""
    sha_info = f" [{args.sha[:7]}]" if args.sha else ""
    print(f"{args.ticket} → {args.step}{pr_info}{sha_info}")

    # Remote sync
    if args.step == "done":
        _remote_delete("sessions", "ticket", args.ticket)
    else:
        _remote_upsert("sessions", "ticket", args.ticket, {
            "step": args.step, "pr": args.pr or 0,
            "updated_at": now,
        })
    _remote_push("milestones", {
        "ticket": args.ticket, "step": args.step,
        "instance_id": row["instance_id"], "project": row["project"],
        "pr": args.pr or 0, "sha": args.sha or "", "detail": args.detail or "",
        "event_at": now,
    })


def cmd_pause(args: argparse.Namespace) -> None:
    args.step = "paused"
    args.pr = None
    args.sha = None
    args.detail = args.reason
    cmd_step(args)


def cmd_done(args: argparse.Namespace) -> None:
    args.step = "done"
    args.pr = None
    args.sha = None
    args.detail = None
    cmd_step(args)


def cmd_block(args: argparse.Namespace) -> None:
    args.step = "blocked"
    args.pr = None
    args.sha = None
    args.detail = args.reason
    cmd_step(args)


# ── Query commands ────────────────────────────────────────────────


def cmd_ls(args: argparse.Namespace) -> None:
    conn = _connect()
    query = "SELECT * FROM sessions WHERE 1=1"
    params: list = []

    if args.project:
        query += " AND project=?"
        params.append(args.project)
    if args.mine:
        query += " AND host=?"
        params.append(_hostname())

    query += " ORDER BY updated_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("No active sessions.")
        return

    # Table format
    print(f"{'INSTANCE':<20} {'ROLE':<12} {'TICKET':<12} {'STEP':<14} {'PR':<6} {'SOURCE':<8} {'UPDATED':<20}")
    print("─" * 92)
    for r in rows:
        pr = str(r["pr"]) if r["pr"] else "—"
        print(f"{r['instance_id']:<20} {r['role']:<12} {r['ticket'] or '—':<12} {r['step']:<14} {pr:<6} {r['source']:<8} {r['updated_at']:<20}")


def cmd_history(args: argparse.Namespace) -> None:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM milestones WHERE ticket=? ORDER BY created_at ASC",
        (args.ticket,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No milestones for {args.ticket}.")
        return

    print(f"History for {args.ticket}:")
    print(f"{'TIME':<22} {'STEP':<14} {'INSTANCE':<20} {'PR':<6} {'SHA':<10} {'DETAIL'}")
    print("─" * 90)
    for r in rows:
        pr = str(r["pr"]) if r["pr"] else "—"
        sha = r["sha"][:7] if r["sha"] else "—"
        detail = r["detail"] or ""
        print(f"{r['created_at']:<22} {r['step']:<14} {r['instance_id']:<20} {pr:<6} {sha:<10} {detail}")


# ── Claim commands ────────────────────────────────────────────────


def cmd_claim(args: argparse.Namespace) -> None:
    now = _now()
    instance_id = args.instance or f"t{int(time.time()) % 100000}-{os.urandom(2).hex()}"

    conn = _connect()
    try:
        conn.execute("BEGIN EXCLUSIVE")

        if args.mega and args.phase is not None:
            # MEGA phase claim
            claim_id = f"{args.mega}-phase-{args.phase}"
            row = conn.execute(
                "SELECT owner FROM claims WHERE id=? AND owner IS NULL", (claim_id,)
            ).fetchone()
            if row is None:
                existing = conn.execute("SELECT owner FROM claims WHERE id=?", (claim_id,)).fetchone()
                if existing:
                    print(f"Phase {args.phase} of {args.mega} already claimed by {existing['owner']}", file=sys.stderr)
                else:
                    print(f"Claim {claim_id} not found. Create MEGA phases first.", file=sys.stderr)
                conn.rollback()
                sys.exit(1)
            conn.execute(
                "UPDATE claims SET owner=?, pid=?, host=?, branch=?, claimed_at=? WHERE id=?",
                (instance_id, os.getpid(), _hostname(), args.branch, now, claim_id),
            )
        else:
            # Standalone claim
            claim_id = args.ticket
            existing = conn.execute("SELECT owner FROM claims WHERE id=?", (claim_id,)).fetchone()
            if existing and existing["owner"]:
                print(f"{args.ticket} already claimed by {existing['owner']}", file=sys.stderr)
                conn.rollback()
                sys.exit(1)
            conn.execute(
                """INSERT OR REPLACE INTO claims (id, ticket, phase, mega_id, owner, pid, host, branch, deps, claimed_at, completed_at)
                   VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, NULL, ?, NULL)""",
                (claim_id, args.ticket, instance_id, os.getpid(), _hostname(), args.branch, now),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Claimed: {claim_id} → {instance_id}")

    # Dual-write: also create .claude/claims/ JSON for backward compatibility
    _dual_write_claim_json(args, instance_id, now)

    # Remote sync
    _remote_upsert("claims", "claim_id", claim_id, {
        "claim_id": claim_id, "ticket": args.ticket,
        "phase": args.phase, "mega_id": args.mega or "",
        "owner": instance_id, "pid": os.getpid(),
        "host": _hostname(), "branch": args.branch or "",
        "claimed_at": now,
    })


def cmd_release(args: argparse.Namespace) -> None:
    now = _now()
    conn = _connect()

    if args.phase is not None:
        claim_id = f"{args.ticket}-phase-{args.phase}"
    else:
        claim_id = args.ticket

    updated = conn.execute(
        "UPDATE claims SET owner=NULL, pid=NULL, completed_at=? WHERE id=?",
        (now, claim_id),
    ).rowcount

    if updated == 0:
        print(f"Claim {claim_id} not found.", file=sys.stderr)
        sys.exit(1)

    conn.commit()
    conn.close()
    print(f"Released: {claim_id}")

    # Remote sync
    _remote_upsert("claims", "claim_id", claim_id, {
        "owner": "", "pid": 0, "completed_at": now,
    })


def cmd_claims(args: argparse.Namespace) -> None:
    conn = _connect()

    if args.mega_id:
        rows = conn.execute(
            "SELECT * FROM claims WHERE mega_id=? ORDER BY phase ASC", (args.mega_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM claims WHERE completed_at IS NULL ORDER BY claimed_at DESC"
        ).fetchall()

    conn.close()

    if not rows:
        print("No active claims." if not args.mega_id else f"No claims for {args.mega_id}.")
        return

    print(f"{'ID':<30} {'TICKET':<12} {'OWNER':<20} {'HOST':<18} {'CLAIMED':<22} {'DONE'}")
    print("─" * 110)
    for r in rows:
        owner = r["owner"] or "—"
        host = r["host"] or "—"
        claimed = r["claimed_at"] or "—"
        done = r["completed_at"] or "—"
        print(f"{r['id']:<30} {r['ticket']:<12} {owner:<20} {host:<18} {claimed:<22} {done}")


def cmd_init_mega(args: argparse.Namespace) -> None:
    """Initialize MEGA phases from a JSON definition or inline args."""
    conn = _connect()
    tickets_list = [t.strip() for t in args.tickets.split(",")] if args.tickets else []
    deps_list = [int(d.strip()) for d in args.deps.split(",")] if args.deps else []

    claim_id = f"{args.mega}-phase-{args.phase}"
    conn.execute(
        """INSERT OR REPLACE INTO claims (id, ticket, phase, mega_id, owner, pid, host, branch, deps, claimed_at, completed_at)
           VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL)""",
        (claim_id, ",".join(tickets_list), args.phase, args.mega, json.dumps(deps_list)),
    )
    conn.commit()
    conn.close()
    print(f"MEGA phase initialized: {claim_id} (tickets: {tickets_list}, deps: {deps_list})")


# ── Maintenance ───────────────────────────────────────────────────


def cmd_cleanup(args: argparse.Namespace) -> None:
    hours = int(args.stale.rstrip("h"))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = _connect()

    # Stale sessions
    stale_sessions = conn.execute(
        "SELECT instance_id, ticket FROM sessions WHERE updated_at < ?", (cutoff,)
    ).fetchall()
    if stale_sessions:
        conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
        for s in stale_sessions:
            print(f"Cleaned session: {s['instance_id']} ({s['ticket']})")

    # Stale claims (claimed but not completed, old)
    stale_claims = conn.execute(
        "SELECT id, owner FROM claims WHERE owner IS NOT NULL AND completed_at IS NULL AND claimed_at < ?",
        (cutoff,),
    ).fetchall()
    if stale_claims:
        conn.execute(
            "UPDATE claims SET owner=NULL, pid=NULL WHERE owner IS NOT NULL AND completed_at IS NULL AND claimed_at < ?",
            (cutoff,),
        )
        for c in stale_claims:
            print(f"Released stale claim: {c['id']} (was {c['owner']})")

    if not stale_sessions and not stale_claims:
        print(f"Nothing stale (cutoff: {hours}h).")

    conn.commit()
    conn.close()


# ── Dual-write backward compat ───────────────────────────────────


def _dual_write_claim_json(args: argparse.Namespace, instance_id: str, now: str) -> None:
    """Write .claude/claims/ JSON for backward compatibility with existing rules."""
    claims_dir = Path.cwd() / ".claude" / "claims"
    if not claims_dir.exists():
        return  # not in a stoa repo, skip

    if args.mega:
        # Don't dual-write MEGA phases (too complex, let existing JSON handle it)
        return

    claim_file = claims_dir / f"{args.ticket}.json"
    data = {
        "ticket": args.ticket,
        "title": "",
        "owner": instance_id,
        "pid": os.getpid(),
        "hostname": _hostname(),
        "claimed_at": now,
        "branch": args.branch or "",
        "completed_at": None,
    }
    claim_file.write_text(json.dumps(data, indent=2) + "\n")


# ── Remote query ──────────────────────────────────────────────────


def cmd_remote_ls(args: argparse.Namespace) -> None:
    """List sessions from PocketBase remote."""
    if not _remote_enabled():
        print("Remote not configured. Set HEGEMON_REMOTE_URL + HEGEMON_REMOTE_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    token = _remote_auth()
    if not token:
        print("Failed to authenticate with PocketBase.", file=sys.stderr)
        sys.exit(1)

    try:
        params = "perPage=50&sort=-updated_at"
        if args.project:
            params += f'&filter=project="{args.project}"'
        req = urllib.request.Request(
            f"{REMOTE_URL}/api/collections/sessions/records?{params}",
            headers={"Authorization": token},
        )
        resp = urllib.request.urlopen(req, timeout=10, context=_ssl_context())
        result = json.loads(resp.read())
    except Exception as e:
        print(f"Remote query failed: {e}", file=sys.stderr)
        sys.exit(1)

    items = result.get("items", [])
    if not items:
        print("No remote sessions.")
        return

    print(f"Remote sessions ({REMOTE_URL}):")
    print(f"{'INSTANCE':<20} {'ROLE':<12} {'TICKET':<12} {'STEP':<14} {'PR':<6} {'SOURCE':<8} {'UPDATED':<20}")
    print("─" * 92)
    for r in items:
        pr = str(r.get("pr", 0)) if r.get("pr") else "—"
        print(f"{r.get('instance_id','?'):<20} {r.get('role','?'):<12} {r.get('ticket','—'):<12} {r.get('step','?'):<14} {pr:<6} {r.get('source','?'):<8} {r.get('updated_at','?'):<20}")


def cmd_sync(args: argparse.Namespace) -> None:
    """Full sync: push all local sessions + claims to PocketBase."""
    if not _remote_enabled():
        print("Remote not configured. Set HEGEMON_REMOTE_URL + HEGEMON_REMOTE_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    conn = _connect()

    # Sync sessions
    sessions = conn.execute("SELECT * FROM sessions").fetchall()
    synced = 0
    for s in sessions:
        _remote_upsert("sessions", "instance_id", s["instance_id"], {
            "instance_id": s["instance_id"], "project": s["project"],
            "role": s["role"], "ticket": s["ticket"] or "",
            "branch": s["branch"] or "", "step": s["step"],
            "pr": s["pr"] or 0, "host": s["host"] or "",
            "source": s["source"], "pid": s["pid"] or 0,
            "started_at": s["started_at"], "updated_at": s["updated_at"],
        })
        synced += 1

    # Sync active claims
    claims = conn.execute(
        "SELECT * FROM claims WHERE completed_at IS NULL"
    ).fetchall()
    claims_synced = 0
    for c in claims:
        _remote_upsert("claims", "claim_id", c["id"], {
            "claim_id": c["id"], "ticket": c["ticket"],
            "phase": c["phase"], "mega_id": c["mega_id"] or "",
            "owner": c["owner"] or "", "pid": c["pid"] or 0,
            "host": c["host"] or "", "branch": c["branch"] or "",
            "deps": c["deps"] or "", "claimed_at": c["claimed_at"] or "",
        })
        claims_synced += 1

    conn.close()
    print(f"Synced to {REMOTE_URL}: {synced} sessions, {claims_synced} claims")


# ── Import existing claims ────────────────────────────────────────


def cmd_import_claims(args: argparse.Namespace) -> None:
    """Import existing .claude/claims/*.json into SQLite."""
    claims_dir = Path(args.path)
    if not claims_dir.exists():
        print(f"Claims directory not found: {claims_dir}", file=sys.stderr)
        sys.exit(1)

    conn = _connect()
    imported = 0

    for f in sorted(claims_dir.glob("*.json")):
        data = json.loads(f.read_text())

        if "mega" in data:
            # MEGA claim with phases
            for phase in data.get("phases", []):
                claim_id = f"{data['mega']}-phase-{phase['id']}"
                tickets = ",".join(phase.get("tickets", []))
                deps = json.dumps(phase.get("deps", []))
                conn.execute(
                    """INSERT OR REPLACE INTO claims
                       (id, ticket, phase, mega_id, owner, pid, host, branch, deps, claimed_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
                    (claim_id, tickets, phase["id"], data["mega"],
                     phase.get("owner"), phase.get("hostname"),
                     phase.get("branch"), deps,
                     phase.get("claimed_at"), phase.get("completed_at")),
                )
                imported += 1
        elif "ticket" in data:
            # Standalone claim
            conn.execute(
                """INSERT OR REPLACE INTO claims
                   (id, ticket, phase, mega_id, owner, pid, host, branch, deps, claimed_at, completed_at)
                   VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, NULL, ?, ?)""",
                (data["ticket"], data["ticket"],
                 data.get("owner"), data.get("pid"),
                 data.get("hostname"), data.get("branch"),
                 data.get("claimed_at"), data.get("completed_at")),
            )
            imported += 1

    conn.commit()
    conn.close()
    print(f"Imported {imported} claims from {claims_dir}")


# ── Ticket commands ───────────────────────────────────────────────


def cmd_ticket_upsert(args: argparse.Namespace) -> None:
    now = _now()
    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO tickets
           (id, title, status, estimate, priority, component, summary, dod_items, parent_id, cycle, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (args.ticket, args.title, args.status, args.estimate, args.priority,
         args.component, args.summary, args.dod, args.parent, args.cycle, now),
    )
    conn.commit()
    conn.close()
    print(f"Ticket upserted: {args.ticket} ({args.status or '?'})")

    # Remote sync
    _remote_upsert("tickets", "ticket_id", args.ticket, {
        "ticket_id": args.ticket, "title": args.title or "",
        "status": args.status or "", "estimate": args.estimate or 0,
        "priority": args.priority or 0, "component": args.component or "",
        "summary": args.summary or "", "dod_items": args.dod or "[]",
        "parent_id": args.parent or "", "cycle": args.cycle or "",
        "updated_at": now,
    })


def cmd_ticket_ls(args: argparse.Namespace) -> None:
    conn = _connect()
    query = "SELECT * FROM tickets WHERE 1=1"
    params: list = []

    if args.cycle:
        query += " AND cycle=?"
        params.append(args.cycle)
    if args.status:
        query += " AND status=?"
        params.append(args.status)
    if args.component:
        query += " AND component=?"
        params.append(args.component)

    query += " ORDER BY priority ASC, id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("No tickets found.")
        return

    print(f"{'ID':<14} {'STATUS':<14} {'EST':<5} {'PRI':<5} {'COMPONENT':<12} {'CYCLE':<10} {'TITLE'}")
    print("-" * 90)
    for r in rows:
        est = str(r["estimate"]) if r["estimate"] else "-"
        pri = str(r["priority"]) if r["priority"] else "-"
        component = r["component"] or "-"
        cycle = r["cycle"] or "-"
        title = (r["title"] or "")[:40]
        print(f"{r['id']:<14} {r['status'] or '-':<14} {est:<5} {pri:<5} {component:<12} {cycle:<10} {title}")


def cmd_ticket_sync(args: argparse.Namespace) -> None:
    """Pull all records from PocketBase tickets collection into local SQLite."""
    if not _remote_enabled():
        print("Remote not configured. Set HEGEMON_REMOTE_URL + HEGEMON_REMOTE_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    token = _remote_auth()
    if not token:
        print("Failed to authenticate with PocketBase.", file=sys.stderr)
        sys.exit(1)

    try:
        page = 1
        total_synced = 0
        conn = _connect()

        while True:
            req = urllib.request.Request(
                f"{REMOTE_URL}/api/collections/tickets/records?perPage=100&page={page}",
                headers={"Authorization": token},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            items = result.get("items", [])

            if not items:
                break

            for item in items:
                conn.execute(
                    """INSERT OR REPLACE INTO tickets
                       (id, title, status, estimate, priority, component, summary, dod_items, parent_id, cycle, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item.get("ticket_id", item.get("id", "")),
                     item.get("title", ""),
                     item.get("status", ""),
                     item.get("estimate"),
                     item.get("priority"),
                     item.get("component", ""),
                     item.get("summary", ""),
                     item.get("dod_items", "[]"),
                     item.get("parent_id", ""),
                     item.get("cycle", ""),
                     item.get("updated_at", _now())),
                )
                total_synced += 1

            if len(items) < 100:
                break
            page += 1

        conn.commit()
        conn.close()
        print(f"Synced {total_synced} tickets from {REMOTE_URL}")

    except Exception as e:
        print(f"Remote sync failed: {e}", file=sys.stderr)
        sys.exit(1)


# ── Council cache commands ────────────────────────────────────────


def cmd_council_cache(args: argparse.Namespace) -> None:
    now = _now()
    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO council_cache
           (ticket_id, score, verdict, personas, ticket_hash, evaluated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (args.ticket, args.score, args.verdict, args.personas, args.hash, now),
    )
    conn.commit()
    conn.close()
    print(f"Council cached: {args.ticket} → {args.score}/10 {args.verdict}")

    # Remote sync
    _remote_upsert("council_cache", "ticket_id", args.ticket, {
        "ticket_id": args.ticket, "score": args.score,
        "verdict": args.verdict, "personas": args.personas or "{}",
        "ticket_hash": args.hash or "", "evaluated_at": now,
    })


def cmd_council_check(args: argparse.Namespace) -> None:
    conn = _connect()
    row = conn.execute(
        "SELECT score, verdict, evaluated_at FROM council_cache WHERE ticket_id=? AND ticket_hash=?",
        (args.ticket, args.hash),
    ).fetchone()
    conn.close()

    if row:
        result = {
            "hit": True,
            "score": row["score"],
            "verdict": row["verdict"],
            "evaluated_at": row["evaluated_at"],
        }
    else:
        result = {"hit": False}

    print(json.dumps(result))


# ── Brief command ─────────────────────────────────────────────────


def cmd_brief(args: argparse.Namespace) -> None:
    project = args.project or os.environ.get("HEGEMON_PROJECT", "stoa")
    conn = _connect()

    # Active sessions for this host
    sessions = conn.execute(
        "SELECT instance_id, role, ticket, step, pr FROM sessions WHERE host=? AND project=?",
        (_hostname(), project),
    ).fetchall()

    # Non-done tickets in current/next cycles (limit 20)
    tickets = conn.execute(
        "SELECT id, title, status, estimate, component, summary FROM tickets WHERE status != 'Done' AND cycle IN ('current', 'next') ORDER BY priority ASC, id ASC LIMIT 20",
    ).fetchall()

    # Active claims
    claims = conn.execute(
        "SELECT id, ticket, owner, phase FROM claims WHERE owner IS NOT NULL AND completed_at IS NULL",
    ).fetchall()

    # Recent milestones (last 24h, limit 10)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    milestones = conn.execute(
        "SELECT ticket, step, pr, created_at FROM milestones WHERE created_at > ? ORDER BY created_at DESC LIMIT 10",
        (cutoff,),
    ).fetchall()

    conn.close()

    brief = {
        "generated_at": _now(),
        "project": project,
        "sessions": [
            {"instance_id": s["instance_id"], "role": s["role"],
             "ticket": s["ticket"], "step": s["step"], "pr": s["pr"]}
            for s in sessions
        ],
        "tickets": [
            {"id": t["id"], "title": t["title"], "status": t["status"],
             "estimate": t["estimate"], "component": t["component"],
             "summary": t["summary"]}
            for t in tickets
        ],
        "claims": [
            {"id": c["id"], "ticket": c["ticket"], "owner": c["owner"],
             "phase": c["phase"]}
            for c in claims
        ],
        "recent_milestones": [
            {"ticket": m["ticket"], "step": m["step"], "pr": m["pr"],
             "created_at": m["created_at"]}
            for m in milestones
        ],
    }

    print(json.dumps(brief, indent=2))


# ── Queue commands ────────────────────────────────────────────────

VALID_QUEUE_STATUSES = ["pending", "dispatched", "running", "done", "failed", "cancelled"]


def cmd_queue(args: argparse.Namespace) -> None:
    """Dispatch to queue subcommand."""
    queue_commands = {
        "add": cmd_queue_add,
        "ls": cmd_queue_ls,
        "next": cmd_queue_next,
        "dispatch": cmd_queue_dispatch,
        "done": cmd_queue_done,
        "fail": cmd_queue_fail,
        "cancel": cmd_queue_cancel,
        "flush": cmd_queue_flush,
        "stats": cmd_queue_stats,
        "current": cmd_queue_current,
    }
    handler = queue_commands.get(args.queue_command)
    if handler:
        handler(args)
    else:
        print(f"Unknown queue command: {args.queue_command}", file=sys.stderr)
        sys.exit(1)


def cmd_queue_add(args: argparse.Namespace) -> None:
    """Enqueue one or more tickets."""
    conn = _connect()
    now = _now()
    priority = args.priority if args.priority is not None else 2
    role = args.role

    added = 0
    for ticket_id in args.tickets:
        ticket_id = ticket_id.strip().upper()
        if not ticket_id:
            continue
        conn.execute(
            """INSERT INTO queue_jobs (ticket_id, title, priority, role, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (ticket_id, args.title or "", priority, role, now),
        )
        added += 1

    conn.commit()
    conn.close()
    role_info = f" (role: {role})" if role else ""
    print(f"Enqueued {added} job(s) at priority {priority}{role_info}")


def cmd_queue_ls(args: argparse.Namespace) -> None:
    """List queue jobs."""
    conn = _connect()
    if args.all:
        rows = conn.execute(
            "SELECT * FROM queue_jobs ORDER BY priority ASC, id ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM queue_jobs WHERE status IN ('pending', 'dispatched', 'running') ORDER BY priority ASC, id ASC"
        ).fetchall()
    conn.close()

    if not rows:
        print("Queue empty.")
        return

    print(f"{'ID':<6} {'TICKET':<14} {'PRI':<5} {'STATUS':<12} {'ROLE':<10} {'ASSIGNED':<14} {'CREATED':<20}")
    print("─" * 81)
    for r in rows:
        role = r["role"] or "any"
        assigned = r["assigned_to"] or "—"
        print(f"{r['id']:<6} {r['ticket_id']:<14} {r['priority']:<5} {r['status']:<12} {role:<10} {assigned:<14} {r['created_at']:<20}")


def cmd_queue_next(args: argparse.Namespace) -> None:
    """Peek at the next pending job matching the role filter."""
    conn = _connect()

    if args.role:
        row = conn.execute(
            """SELECT * FROM queue_jobs
               WHERE status = 'pending'
                 AND (role IS NULL OR role = ?)
               ORDER BY priority ASC, id ASC
               LIMIT 1""",
            (args.role,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT * FROM queue_jobs
               WHERE status = 'pending'
               ORDER BY priority ASC, id ASC
               LIMIT 1""",
        ).fetchone()

    conn.close()

    if not row:
        if args.format == "json":
            print("")
        else:
            print("No pending jobs.")
        return

    if args.format == "json":
        print(json.dumps({
            "id": row["id"], "ticket_id": row["ticket_id"],
            "priority": row["priority"], "role": row["role"],
            "title": row["title"],
        }))
    else:
        print(f"Next: #{row['id']} {row['ticket_id']} (P{row['priority']}, role: {row['role'] or 'any'})")


def cmd_queue_dispatch(args: argparse.Namespace) -> None:
    """Mark a job as dispatched to a worker."""
    now = _now()
    conn = _connect()
    updated = conn.execute(
        "UPDATE queue_jobs SET status='dispatched', assigned_to=?, dispatched_at=? WHERE id=? AND status='pending'",
        (args.worker, now, args.job_id),
    ).rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        print(f"Job #{args.job_id} not found or not pending.", file=sys.stderr)
        sys.exit(1)
    print(f"Job #{args.job_id} dispatched to {args.worker}")


def cmd_queue_done(args: argparse.Namespace) -> None:
    """Mark a job as completed."""
    now = _now()
    conn = _connect()
    updated = conn.execute(
        "UPDATE queue_jobs SET status='done', completed_at=? WHERE id=? AND status IN ('pending', 'dispatched', 'running')",
        (now, args.job_id),
    ).rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        print(f"Job #{args.job_id} not found or already finished.", file=sys.stderr)
        sys.exit(1)
    print(f"Job #{args.job_id} done")


def cmd_queue_fail(args: argparse.Namespace) -> None:
    """Mark a job as failed."""
    now = _now()
    conn = _connect()
    updated = conn.execute(
        "UPDATE queue_jobs SET status='failed', completed_at=?, error=? WHERE id=? AND status IN ('pending', 'dispatched', 'running')",
        (now, args.reason, args.job_id),
    ).rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        print(f"Job #{args.job_id} not found or already finished.", file=sys.stderr)
        sys.exit(1)
    print(f"Job #{args.job_id} failed: {args.reason}")


def cmd_queue_cancel(args: argparse.Namespace) -> None:
    """Cancel a pending job."""
    now = _now()
    conn = _connect()
    updated = conn.execute(
        "UPDATE queue_jobs SET status='cancelled', completed_at=? WHERE id=? AND status='pending'",
        (now, args.job_id),
    ).rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        print(f"Job #{args.job_id} not found or not pending.", file=sys.stderr)
        sys.exit(1)
    print(f"Job #{args.job_id} cancelled")


def cmd_queue_flush(args: argparse.Namespace) -> None:
    """Cancel all pending jobs."""
    now = _now()
    conn = _connect()
    count = conn.execute(
        "UPDATE queue_jobs SET status='cancelled', completed_at=? WHERE status='pending'",
        (now,),
    ).rowcount
    conn.commit()
    conn.close()
    print(f"Flushed {count} pending job(s)")


def cmd_queue_stats(args: argparse.Namespace) -> None:
    """Show queue summary."""
    conn = _connect()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM queue_jobs GROUP BY status"
    ).fetchall()
    conn.close()

    if not rows:
        print("Queue empty.")
        return

    counts = {r["status"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    parts = []
    for status in ["pending", "dispatched", "running", "done", "failed", "cancelled"]:
        if counts.get(status, 0) > 0:
            parts.append(f"{counts[status]} {status}")
    print(f"Queue: {total} total — {', '.join(parts)}")


def cmd_queue_current(args: argparse.Namespace) -> None:
    """Print the current running/dispatched job ID for this host (used by stop hook)."""
    conn = _connect()
    host = _hostname()
    row = conn.execute(
        "SELECT id FROM queue_jobs WHERE assigned_to=? AND status IN ('dispatched', 'running') ORDER BY dispatched_at DESC LIMIT 1",
        (host,),
    ).fetchone()
    conn.close()

    if row:
        print(row["id"])
    else:
        # No current job — exit silently (stop hook uses this with || true)
        pass


# ── Main ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(prog="heg-state", description="HEGEMON Agent State Store")
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p = sub.add_parser("start", help="Register a new session")
    p.add_argument("--ticket", "-t")
    p.add_argument("--role", "-r", choices=VALID_ROLES)
    p.add_argument("--branch", "-b")
    p.add_argument("--project", "-p")
    p.add_argument("--instance", "-i")
    p.add_argument("--source", "-s", choices=VALID_SOURCES)

    # step
    p = sub.add_parser("step", help="Update ticket step")
    p.add_argument("ticket")
    p.add_argument("step", choices=VALID_STEPS)
    p.add_argument("--pr", type=int)
    p.add_argument("--sha")
    p.add_argument("--detail")

    # pause
    p = sub.add_parser("pause", help="Mark session as paused")
    p.add_argument("ticket")
    p.add_argument("--reason")

    # done
    p = sub.add_parser("done", help="Mark ticket as done and remove session")
    p.add_argument("ticket")

    # block
    p = sub.add_parser("block", help="Mark ticket as blocked")
    p.add_argument("ticket")
    p.add_argument("--reason", required=True)

    # ls
    p = sub.add_parser("ls", help="List active sessions")
    p.add_argument("--project", "-p")
    p.add_argument("--mine", action="store_true")

    # history
    p = sub.add_parser("history", help="Show milestones for a ticket")
    p.add_argument("ticket")

    # claim
    p = sub.add_parser("claim", help="Claim a ticket or MEGA phase")
    p.add_argument("ticket")
    p.add_argument("--phase", type=int)
    p.add_argument("--mega")
    p.add_argument("--branch", "-b")
    p.add_argument("--tickets", help="Comma-separated ticket IDs for MEGA phase")
    p.add_argument("--instance", "-i")

    # release
    p = sub.add_parser("release", help="Release a claim")
    p.add_argument("ticket")
    p.add_argument("--phase", type=int)

    # claims
    p = sub.add_parser("claims", help="List active claims")
    p.add_argument("mega_id", nargs="?")

    # init-mega
    p = sub.add_parser("init-mega", help="Initialize a MEGA phase")
    p.add_argument("mega")
    p.add_argument("--phase", type=int, required=True)
    p.add_argument("--tickets", default="")
    p.add_argument("--deps", default="")

    # cleanup
    p = sub.add_parser("cleanup", help="Remove stale sessions and claims")
    p.add_argument("--stale", default="2h", help="Stale threshold (e.g., 2h, 24h)")

    # import
    p = sub.add_parser("import-claims", help="Import .claude/claims/*.json into SQLite")
    p.add_argument("--path", default=".claude/claims")

    # remote-ls
    p = sub.add_parser("remote-ls", help="List sessions from PocketBase remote")
    p.add_argument("--project", "-p")

    # sync
    p = sub.add_parser("sync", help="Full sync: push local state to PocketBase")

    # brief
    p = sub.add_parser("brief", help="Compact JSON summary of current state")
    p.add_argument("--project", "-p")

    # ticket-upsert
    p = sub.add_parser("ticket-upsert", help="Create or update a ticket")
    p.add_argument("ticket")
    p.add_argument("--title", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--estimate", type=int)
    p.add_argument("--priority", type=int)
    p.add_argument("--component")
    p.add_argument("--summary")
    p.add_argument("--dod", help="JSON array of DoD criteria")
    p.add_argument("--parent")
    p.add_argument("--cycle")

    # ticket-ls
    p = sub.add_parser("ticket-ls", help="List tickets with optional filters")
    p.add_argument("--cycle")
    p.add_argument("--status")
    p.add_argument("--component")

    # ticket-sync
    p = sub.add_parser("ticket-sync", help="Pull tickets from PocketBase into local SQLite")

    # council-cache
    p = sub.add_parser("council-cache", help="Cache a council evaluation result")
    p.add_argument("ticket")
    p.add_argument("--score", type=float, required=True)
    p.add_argument("--verdict", required=True, choices=["Go", "Fix", "Redo"])
    p.add_argument("--hash", required=True, help="sha256(title + description)")
    p.add_argument("--personas", help="JSON object {persona: score}")

    # council-check
    p = sub.add_parser("council-check", help="Check council cache for a ticket")
    p.add_argument("ticket")
    p.add_argument("--hash", required=True, help="sha256(title + description)")

    # queue (with subcommands)
    p = sub.add_parser("queue", help="Priority FIFO job queue")
    qsub = p.add_subparsers(dest="queue_command", required=True)

    # queue add
    qp = qsub.add_parser("add", help="Enqueue tickets")
    qp.add_argument("tickets", nargs="+", help="Ticket IDs (e.g., CAB-1550 CAB-1551)")
    qp.add_argument("--priority", "-p", type=int, choices=[0, 1, 2, 3],
                     help="0=urgent, 1=high, 2=normal (default), 3=low")
    qp.add_argument("--role", "-r", choices=VALID_ROLES, help="Target worker role")
    qp.add_argument("--title", "-t", help="Ticket title (optional)")

    # queue ls
    qp = qsub.add_parser("ls", help="List queue jobs")
    qp.add_argument("--all", "-a", action="store_true", help="Include done/failed/cancelled")

    # queue next
    qp = qsub.add_parser("next", help="Peek next pending job")
    qp.add_argument("--role", "-r", choices=VALID_ROLES, help="Filter by worker role")
    qp.add_argument("--format", "-f", choices=["text", "json"], default="text")

    # queue dispatch
    qp = qsub.add_parser("dispatch", help="Mark job as dispatched to a worker")
    qp.add_argument("job_id", type=int)
    qp.add_argument("worker", help="Worker hostname or role name")

    # queue done
    qp = qsub.add_parser("done", help="Mark job as completed")
    qp.add_argument("job_id", type=int)

    # queue fail
    qp = qsub.add_parser("fail", help="Mark job as failed")
    qp.add_argument("job_id", type=int)
    qp.add_argument("reason", help="Failure reason")

    # queue cancel
    qp = qsub.add_parser("cancel", help="Cancel a pending job")
    qp.add_argument("job_id", type=int)

    # queue flush
    qsub.add_parser("flush", help="Cancel all pending jobs")

    # queue stats
    qsub.add_parser("stats", help="Show queue summary counts")

    # queue current
    qsub.add_parser("current", help="Print current job ID for this host")

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "step": cmd_step,
        "pause": cmd_pause,
        "done": cmd_done,
        "block": cmd_block,
        "ls": cmd_ls,
        "history": cmd_history,
        "claim": cmd_claim,
        "release": cmd_release,
        "claims": cmd_claims,
        "init-mega": cmd_init_mega,
        "cleanup": cmd_cleanup,
        "import-claims": cmd_import_claims,
        "remote-ls": cmd_remote_ls,
        "sync": cmd_sync,
        "brief": cmd_brief,
        "ticket-upsert": cmd_ticket_upsert,
        "ticket-ls": cmd_ticket_ls,
        "ticket-sync": cmd_ticket_sync,
        "council-cache": cmd_council_cache,
        "council-check": cmd_council_check,
        "queue": cmd_queue,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
