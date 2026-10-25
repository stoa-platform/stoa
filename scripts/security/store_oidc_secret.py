#!/usr/bin/env python3
"""Store a Keycloak client-secret response through stdin, without echoing it."""

import argparse
import base64
import json
import secrets
import subprocess
import sys


def command(args: list[str], body: str | None = None) -> str:
    result = subprocess.run(args, input=body, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Secret storage command failed; output withheld.")
    return result.stdout


def store(args, value: str) -> None:
    if args.vault_path:
        command(["vault", "kv", "patch", args.vault_path, "-"], json.dumps({args.key: value}))
        return
    existing = command(
        [
            "kubectl",
            "get",
            "secret",
            args.name,
            "-n",
            args.namespace,
            "--ignore-not-found",
            "-o",
            "json",
        ]
    )
    secret = (
        json.loads(existing)
        if existing.strip()
        else {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": args.name, "namespace": args.namespace},
            "data": {},
        }
    )
    data = secret.setdefault("data", {})
    data[args.key] = base64.b64encode(value.encode()).decode()
    if args.client_id:
        data["client-id"] = base64.b64encode(args.client_id.encode()).decode()
    if args.cookie and ("cookie-secret" not in data or args.rotate_cookie):
        # oauth2-proxy decodes this base64 string to a 32-byte encryption key.
        cookie = base64.b64encode(secrets.token_bytes(32)).decode()
        data["cookie-secret"] = base64.b64encode(cookie.encode()).decode()
    if existing.strip():
        command(["kubectl", "replace", "-f", "-"], json.dumps(secret))
    else:
        command(["kubectl", "create", "-f", "-"], json.dumps(secret))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="oauth2-proxy-secret")
    parser.add_argument("--namespace", default="stoa-monitoring")
    parser.add_argument("--key", default="client-secret")
    parser.add_argument("--client-id")
    parser.add_argument("--cookie", action="store_true")
    parser.add_argument("--rotate-cookie", action="store_true")
    parser.add_argument("--vault-path")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384:
            raise ValueError("Input is too large.")
        value = json.loads(raw)["value"]
        if not isinstance(value, str) or not value:
            raise ValueError("A client-secret response is required.")
        if args.rotate_cookie and not args.cookie:
            raise ValueError("Cookie rotation requires --cookie.")
        if args.vault_path and args.cookie:
            raise ValueError(
                "Use the Kubernetes cookie procedure or your vault rotation procedure."
            )
        store(args, value)
    except (ValueError, KeyError, TypeError, OSError):
        print("Secret storage failed; input and command output are withheld.", file=sys.stderr)
        return 1
    print(
        "Secret stored. See docs/runbooks/first-admin-bootstrap.md for verification and rotation."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
