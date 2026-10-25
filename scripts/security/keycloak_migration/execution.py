"""Durable journal creation and verified migration/rollback execution."""

import json
import os
from pathlib import Path

from keycloak_migration.core import MAX_BYTES, MigrationError, require
from keycloak_migration.journal import load_journal
from keycloak_migration.state import expected, preview, read_state, write_state


def create_journal(path, api, ops):
    try:
        raw = json.dumps({"version": 1, "binding": api.binding(), "operations": ops})
        require(len(raw.encode()) <= MAX_BYTES, "Journal exceeds the size limit; nothing applied")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Persist the directory entry before issuing the first remote mutation.
        fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        raise MigrationError(
            "Cannot create a new private rollback journal; nothing applied"
        ) from None


def execute(api, ops, journal, output):
    preview(ops, output)
    # Fail before the first write if any managed field changed since planning.
    for op in ops:
        state, _ = read_state(api, op)
        require(state == expected(op, "before"), "Concurrent managed configuration change; replan")
    create_journal(journal, api, ops)
    for number, op in enumerate(ops, 1):
        state, current = read_state(api, op)
        require(
            state == expected(op, "before"),
            "Concurrent managed configuration change; stop and replan",
        )
        write_state(api, op, "after", current)
        state, _ = read_state(api, op)
        require(
            state == expected(op, "after"), "Write not verified; stop and replan using the journal"
        )
        print(json.dumps({"verified_operation": number}), file=output, flush=True)


def rollback(api, journal, apply, output):
    ops = list(reversed(load_journal(journal, api)))
    pending = []
    # No rollback write until all preconditions pass. Repeating a rollback is safe.
    for op in ops:
        state, _ = read_state(api, op)
        if state == expected(op, "before"):
            continue
        require(
            state == expected(op, "after"),
            "Rollback conflicts with current configuration; manual review required",
        )
        if op["kind"] == "fields":
            require(
                all(c["before"]["exists"] or len(c["key"]) == 2 for c in op["changes"]),
                "Missing original scalar field: manual rollback required",
            )
        pending.append(op)
    preview(pending, output, reverse=True)
    if not apply:
        return
    for number, op in enumerate(pending, 1):
        state, current = read_state(api, op)
        require(state == expected(op, "after"), "Concurrent change during rollback; stop")
        write_state(api, op, "before", current)
        state, _ = read_state(api, op)
        require(
            state == expected(op, "before"), "Rollback write not verified; stop for manual review"
        )
        print(json.dumps({"verified_rollback_operation": number}), file=output, flush=True)
