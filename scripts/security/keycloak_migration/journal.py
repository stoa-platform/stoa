"""Private journal loading and exact operation-surface validation."""

import json
import os
import stat
from urllib.parse import unquote

from keycloak_migration.core import (
    BOUNDS,
    CLIENT_BOUNDS,
    MAPPER_KEYS,
    MAX_BYTES,
    MigrationError,
    identifier,
    keys,
    require,
)
from keycloak_migration.policy import mapper


def validate_operation(op):
    require(isinstance(op, dict) and op.get("kind") in ("fields", "mapper"))
    path = op.get("path")
    require(isinstance(path, str))
    parts = path.split("/")
    if path:
        if path.startswith("/identity-provider/instances/"):
            require(len(parts) == 4 and identifier(unquote(parts[3])) == parts[3])
        else:
            require(len(parts) in (3, 5) and parts[1] in ("clients", "client-scopes"))
            require(identifier(unquote(parts[2])) == parts[2])
            require(len(parts) != 5 or parts[3:] == ["protocol-mappers", "models"])
    if op["kind"] == "mapper":
        keys(op, ("kind", "path", "name", "before", "after"))
        require(len(parts) == 5)
        identifier(op["name"])
        require(op["after"] in (mapper("tenant", op["name"]), mapper("audience", op["name"])))
        if op["before"] is not None:
            require(isinstance(op["before"], dict) and set(op["before"]) == set(MAPPER_KEYS))
            require(op["before"].get("name") == op["name"])
        return
    keys(op, ("kind", "path", "changes"))
    if path == "":
        allowed = {(k,) for k in BOUNDS} | {("resetPasswordAllowed",)}
    elif path.startswith("/identity-provider/"):
        allowed = {("enabled",)}
    else:
        require(len(parts) == 3 and parts[1] == "clients")
        allowed = {
            (k,)
            for k in (
                "redirectUris",
                "webOrigins",
                "standardFlowEnabled",
                "implicitFlowEnabled",
                "directAccessGrantsEnabled",
            )
        }
        allowed |= {
            ("attributes", k)
            for k in (*CLIENT_BOUNDS, "post.logout.redirect.uris", "pkce.code.challenge.method")
        }
    require(isinstance(op["changes"], list) and bool(op["changes"]))
    seen = set()
    for change in op["changes"]:
        keys(change, ("key", "before", "after"))
        require(isinstance(change["key"], list) and all(isinstance(k, str) for k in change["key"]))
        key = tuple(change["key"])
        require(key in allowed and key not in seen)
        seen.add(key)
        for side in ("before", "after"):
            val = change[side]
            require(isinstance(val, dict) and type(val.get("exists")) is bool)
            keys(val, ("exists", "value") if val["exists"] else ("exists",))
        require(change["after"]["exists"])


def load_journal(path, api):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            require(
                stat.S_ISREG(info.st_mode)
                and info.st_mode & 0o077 == 0
                and info.st_uid == os.getuid(),
                "Journal must be private and owned by the operator",
            )
            raw = stream.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES)
            data = json.loads(raw)
        keys(data, ("version", "binding", "operations"))
        require(
            data["version"] == 1 and data["binding"] == api.binding(),
            "Journal belongs to another target or version",
        )
        require(isinstance(data["operations"], list))
        # Reject accidental edits outside the exact migration surface. Journal
        # before-values remain confidential, operator-owned recovery material.
        for op in data["operations"]:
            validate_operation(op)
        return data["operations"]
    except MigrationError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise MigrationError("Cannot read the rollback journal; details withheld") from None
