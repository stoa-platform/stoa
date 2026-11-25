#!/usr/bin/env python3
"""Pre-deployment check: BACKEND_ENCRYPTION_KEY is set in the Control Plane API Secret.

Reads the Kubernetes Secret with kubectl and reports only whether the key is
present, absent or empty. The value is never printed, logged or written to
disk: kubectl's JSON output stays in this process's memory, and kubectl's own
stderr is not echoed.

Exit codes:
  0  key present and non-empty
  1  key absent from the Secret
  2  key present but empty (or not valid base64)
  3  Secret not found
  4  kubectl failed for another reason (access, context, timeout)

Usage:
  check_backend_encryption_key.py [--namespace stoa-system]
      [--secret stoa-control-plane-api-secrets] [--key BACKEND_ENCRYPTION_KEY]
      [--context NAME]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import subprocess
import sys

OK, ABSENT, EMPTY, MISSING_RESOURCE, KUBECTL_ERROR = 0, 1, 2, 3, 4


def classify(document: dict, field: str) -> int:
    data = document.get("data") or {}
    if field not in data:
        return ABSENT
    encoded = data[field] or ""
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return EMPTY
    return OK if decoded.strip() else EMPTY


def fetch_resource(namespace: str, name: str, context: str | None, timeout: float) -> tuple[int, dict | None]:
    command = ["kubectl", "get", "secret", name, "--namespace", namespace, "--output", "json"]
    if context:
        command += ["--context", context]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603 — fixed argv, no shell
    except (OSError, subprocess.TimeoutExpired):
        return KUBECTL_ERROR, None
    if result.returncode != 0:
        return (MISSING_RESOURCE if "NotFound" in result.stderr else KUBECTL_ERROR), None
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError:
        return KUBECTL_ERROR, None
    return OK, document if isinstance(document, dict) else {}


MESSAGES = {
    OK: "present",
    ABSENT: "absent",
    EMPTY: "empty",
    MISSING_RESOURCE: "secret not found",
    KUBECTL_ERROR: "kubectl failed (no details shown)",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--namespace", default="stoa-system")
    # dest names are neutral: they hold resource names, never a value.
    parser.add_argument("--secret", dest="resource", default="stoa-control-plane-api-secrets")
    parser.add_argument("--key", dest="field", default="BACKEND_ENCRYPTION_KEY")
    parser.add_argument("--context", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    status, document = fetch_resource(args.namespace, args.resource, args.context, args.timeout)
    if status == OK and document is not None:
        status = classify(document, args.field)
    del document
    stream = sys.stdout if status == OK else sys.stderr
    print(f"{args.field} in {args.namespace}/{args.resource}: {MESSAGES[status]}", file=stream)
    return status


if __name__ == "__main__":
    sys.exit(main())
