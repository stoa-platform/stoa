"""Read an on-site bootstrap request from stdin or an owned mode-0600 file."""

import argparse
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime

from engine import provision
from transport import Keycloak, Refused


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused("invalid_arguments", 22)


def read_identity(filename: str | None) -> dict:
    if filename:
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid()
            ):
                raise Refused("input_requires_owned_mode_0600", 22)
            raw = stream.read(16385)
    else:
        raw = sys.stdin.read(16385)
    if len(raw) > 16384:
        raise Refused("input_too_large", 22)
    identity = json.loads(raw)
    fields = (
        "username",
        "email",
        "initial_password",
        "bootstrap_id",
        "admin_user",
        "admin_password",
    )
    if not isinstance(identity, dict) or any(
        not isinstance(identity.get(k), str) or not identity[k] for k in fields
    ):
        raise Refused("invalid_input", 22)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", identity["username"]):
        raise Refused("invalid_identity", 22)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", identity["email"]):
        raise Refused("invalid_identity", 22)
    if any(not 32 <= len(identity[k]) <= 128 for k in ("initial_password", "bootstrap_id")):
        raise Refused("initial_values_require_32_to_128_characters", 22)
    return identity


def main() -> int:
    realm = os.environ.get("KEYCLOAK_REALM", "stoa")
    code, reason, user_id = 22, "invalid_input", None
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--input", help="Owned mode-0600 JSON file; otherwise read stdin")
        args = parser.parse_args()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", realm):
            raise Refused("invalid_realm", 22)
        identity = read_identity(args.input)
        kc = Keycloak(
            os.environ.get("KEYCLOAK_URL", "http://localhost:8080"),
            realm,
            identity["admin_user"],
            identity["admin_password"],
        )
        code, reason, user_id = provision(kc, identity)
    except Refused as error:
        code, reason = error.code, error.reason
    except (ValueError, OSError, KeyError, TypeError):
        code, reason = 22, "invalid_input_or_response"
    except Exception:
        code, reason = 23, "bootstrap_failed"
    # Only allowlisted metadata is logged, never input or response bodies.
    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": "first_admin_bootstrap",
                "realm": realm if re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", realm) else "invalid",
                "account_id": user_id,
                "reason": reason,
                "exit_code": code,
            }
        )
    )
    print("Delete the bootstrap Secret or local input file after successful use.")
    return code


if __name__ == "__main__":
    sys.exit(main())
