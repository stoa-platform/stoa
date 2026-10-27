#!/usr/bin/env python3
"""Draft, explicit-policy Keycloak Admin REST reconciler (Python 3.11+, no dependencies).

Dry run is the default. No authentication/password endpoint: a short-lived bearer
is read from stdin. Never run alongside another configuration writer.
"""

import argparse
import http as http
import os as os
import ssl as ssl
import sys
from pathlib import Path

from keycloak_migration.core import (
    BOUNDS as BOUNDS,
    CLIENT_BOUNDS as CLIENT_BOUNDS,
    MAPPER_KEYS as MAPPER_KEYS,
    MAX_BYTES as MAX_BYTES,
    MigrationError as MigrationError,
    exact_uri as exact_uri,
    identifier as identifier,
    keys as keys,
    require as require,
    strings as strings,
)
from keycloak_migration.execution import (
    create_journal as create_journal,
    execute as execute,
    rollback as rollback,
)
from keycloak_migration.journal import (
    load_journal as load_journal,
    validate_operation as validate_operation,
)
from keycloak_migration.operations import (
    field_op as field_op,
    index as index,
    mapper_view as mapper_view,
    reconcile_mappers as reconcile_mappers,
    validate_effective as validate_effective,
    value_at as value_at,
)
from keycloak_migration.planner import plan as plan
from keycloak_migration.policy import (
    mapper as mapper,
    read_policy as read_policy,
    validate_policy as validate_policy,
)
from keycloak_migration.state import (
    expected as expected,
    preview as preview,
    read_state as read_state,
    write_state as write_state,
)
from keycloak_migration.transport import Admin as Admin


def main(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            # argparse normally echoes arbitrary argument values in diagnostics.
            self.exit(2, "ERROR: invalid CLI arguments; details withheld\n")

    parser = SafeParser(description=__doc__)
    parser.add_argument("--url", required=True, help="HTTPS Keycloak base URL; no credentials")
    parser.add_argument("--policy", required=True, help="Explicit, reviewed realm policy JSON")
    parser.add_argument("--apply", action="store_true", help="Enable writes (default: simulation)")
    parser.add_argument(
        "--journal", type=Path, help="New private plan/rollback journal; required for --apply"
    )
    parser.add_argument(
        "--expect-plan", type=Path, help="Reviewed private plan, required for migration --apply"
    )
    parser.add_argument(
        "--rollback", type=Path, help="Existing journal to reverse (simulation by default)"
    )
    args = parser.parse_args(argv)
    try:
        require(not args.apply or args.rollback or args.journal, "--apply requires a new --journal")
        require(
            not (args.rollback and (args.journal or args.expect_plan)),
            "Use either --rollback or plan/journal",
        )
        require(not args.expect_plan or args.apply, "--expect-plan requires --apply")
        require(
            not args.apply or args.rollback or args.expect_plan,
            "Migration --apply requires --expect-plan from a reviewed simulation",
        )
        p = read_policy(args.policy)
        require(
            not sys.stdin.isatty(),
            "Supply a short-lived bearer on stdin; interactive echo is refused",
        )
        token = sys.stdin.read(16386).rstrip("\n")
        api = Admin(args.url, p["realm"], token)
        if args.rollback:
            rollback(api, args.rollback, args.apply, sys.stdout)
        else:
            ops = plan(api, p)
            if args.apply:
                require(
                    load_journal(args.expect_plan, api) == ops,
                    "Current diff differs from the reviewed plan; run a new simulation",
                )
                execute(api, ops, args.journal, sys.stdout)
                require(not plan(api, p), "Postflight detected residual drift; replan")
            else:
                preview(ops, sys.stdout)
                if args.journal:
                    create_journal(args.journal, api, ops)
        return 0
    except (MigrationError, OSError, ValueError, TypeError, KeyError) as error:
        message = (
            str(error)
            if isinstance(error, MigrationError)
            else "Local/API data failure; details withheld"
        )
        print("ERROR: " + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: interrupted; retain the journal and replan", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
