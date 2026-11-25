#!/usr/bin/env python3
"""Pre-deployment check: BACKEND_ENCRYPTION_KEY is set in the Control Plane API Secret.

Reads one field of the Kubernetes Secret with kubectl and reports only whether
it is present, absent, empty, or the public development key. The value is
never printed, logged or written to disk:
- kubectl renders a go-template, so kubectl passes only the requested field to
  the script;
- that field stays in this process's memory and is compared by digest;
- kubectl's own stderr is not echoed.

Exit codes:
  0  key present, non-empty and not the public development key
  1  key absent from the Secret
  2  key present but empty (or not valid base64)
  3  Secret not found
  4  kubectl failed for another reason (access, context, timeout), or an
     invalid key name
  5  key is the public development key published in the repository

Usage:
  check_backend_encryption_key.py [--namespace stoa-system]
      [--secret stoa-control-plane-api-secrets] [--key BACKEND_ENCRYPTION_KEY]
      [--context NAME]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import re
import subprocess
import sys

OK, ABSENT, EMPTY, MISSING_RESOURCE, KUBECTL_ERROR, PUBLISHED_DEFAULT = 0, 1, 2, 3, 4, 5

# SHA-256 of the decoded bytes of the development Fernet key in
# src/services/encryption_service.py (_DEV_FERNET_KEY). Only the digest is kept
# here; a test keeps them in sync.
PUBLISHED_DEFAULT_SHA256 = bytes.fromhex("871ecee010f50d56b7b5cebb47b37839dee920a06eab417a569fb740db0ac3f0")

# Kubernetes Secret data keys: alphanumerics, '-', '_' and '.'. Checked before
# the name is placed in the go-template.
FIELD_NAME = re.compile(r"[-._a-zA-Z0-9]{1,253}")

# Prefix marking "field present" in the template output, so an empty value is
# told apart from an absent field.
PRESENT_MARK = "="


def field_template(field: str) -> str:
    """go-template printing PRESENT_MARK and the base64 data of one field, or nothing."""
    return f'{{{{range $k, $v := .data}}}}{{{{if eq $k "{field}"}}}}{PRESENT_MARK}{{{{$v}}}}{{{{end}}}}{{{{end}}}}'


def classify(rendered: str) -> int:
    """Status of the field from the template output (never returned or printed)."""
    if rendered == "":
        return ABSENT
    if not rendered.startswith(PRESENT_MARK):
        return KUBECTL_ERROR
    encoded = rendered[len(PRESENT_MARK) :]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return EMPTY
    stripped = decoded.strip()
    if not stripped:
        return EMPTY
    # Compare decoded key bytes, decoded the way Fernet decodes its key.
    try:
        decoded_bytes = base64.urlsafe_b64decode(stripped)
    except (binascii.Error, ValueError):
        return OK
    if hmac.compare_digest(hashlib.sha256(decoded_bytes).digest(), PUBLISHED_DEFAULT_SHA256):
        return PUBLISHED_DEFAULT
    return OK


def fetch_field(namespace: str, name: str, field: str, context: str | None, timeout: float) -> tuple[int, str]:
    command = [
        "kubectl",
        "get",
        "secret",
        name,
        "--namespace",
        namespace,
        f"--output=go-template={field_template(field)}",
    ]
    if context:
        command += ["--context", context]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603 — fixed argv, no shell
    except (OSError, subprocess.TimeoutExpired):
        return KUBECTL_ERROR, ""
    if result.returncode != 0:
        return (MISSING_RESOURCE if "NotFound" in result.stderr else KUBECTL_ERROR), ""
    return OK, result.stdout


MESSAGES = {
    OK: "present",
    ABSENT: "absent",
    EMPTY: "empty",
    MISSING_RESOURCE: "secret not found",
    KUBECTL_ERROR: "kubectl failed (no details shown)",
    PUBLISHED_DEFAULT: "public development key (treated as absent)",
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

    if not FIELD_NAME.fullmatch(args.field):
        print("invalid key name", file=sys.stderr)
        return KUBECTL_ERROR

    status, rendered = fetch_field(args.namespace, args.resource, args.field, args.context, args.timeout)
    if status == OK:
        status = classify(rendered)
    del rendered
    stream = sys.stdout if status == OK else sys.stderr
    print(f"{args.field} in {args.namespace}/{args.resource}: {MESSAGES[status]}", file=stream)
    return status


if __name__ == "__main__":
    sys.exit(main())
