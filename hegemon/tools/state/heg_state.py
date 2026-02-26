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
"""

import argparse
import json
import os
import platform
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("HEGEMON_STATE_DB", Path.home() / ".hegemon" / "state.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

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


def _ssl_context() -> ssl.SSLContext:
    """Create SSL context with certifi CA bundle (macOS Python needs this)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


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
            f"{REMOTE_URL}/api/collections/_superusers/auth-with-password",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5, context=_ssl_context())
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
        urllib.request.urlopen(req, timeout=5, context=_ssl_context())
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
        resp = urllib.request.urlopen(req, timeout=5, context=_ssl_context())
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
            urllib.request.urlopen(req, timeout=5, context=_ssl_context())
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
        resp = urllib.request.urlopen(req, timeout=5, context=_ssl_context())
        result = json.loads(resp.read())

        if result.get("totalItems", 0) > 0:
            pb_id = result["items"][0]["id"]
            req = urllib.request.Request(
                f"{REMOTE_URL}/api/collections/{collection}/records/{pb_id}",
                headers={"Authorization": token},
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=5, context=_ssl_context())
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
    if not _tables_exist(conn):
        conn.executescript(SCHEMA_PATH.read_text())
    return conn


def _tables_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()
    return row[0] > 0


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
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
