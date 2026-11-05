#!/usr/bin/env python3
"""Reject sensitive filenames and obvious secrets in staged additions or messages.

This local guard complements the full Gitleaks CI scan. Diagnostics never echo
matched content. Only explicit placeholders and variable references are exempt.
"""

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----",
    "access token": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}\b"
    r"|\bgithub_pat_[A-Za-z0-9_]{22,}\b"
    r"|\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
}
ASSIGNMENT = re.compile(
    r"(?i)\b(?:[A-Z0-9]+[_-])*(?:password|passwd|api[_-]?key|client[_-]?secret|"
    r"access[_-]?token|auth[_-]?token|secret[_-]?key)\b[\"']?\s*[:=]\s*"
    r"(?:[\"']([^\"'\r\n]{8,})[\"']|([A-Za-z0-9_!@%&*+./=-]{8,})(?=\s|$|[,;#]))"
)
PLACEHOLDER = re.compile(
    r"(?:REPLACE_FROM_VAULT|REPLACE_ME|CHANGE_ME|REDACTED|\$\{[^}\r\n]+\}|"
    r"\$[A-Za-z_][A-Za-z0-9_]*|<YOUR_[A-Z0-9_]+>)"
)
# Unquoted identifiers and attribute paths (process.env.API_KEY, formData.password,
# TypeScript "name!") are code references. Bare words with digits stay literals.
REFERENCE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+!?|[A-Za-z_]+!?")
FORBIDDEN = (".env*", "*.pem", "*.key", "*.tfvars", "credentials", "credentials.json")
FORBIDDEN += ("*.credentials", ".git-credentials")
TEMPLATES = (".env*.example", ".env*.sample", ".env*.template")


def check_line(line):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, line):
            return label
    for match in ASSIGNMENT.finditer(line):
        quoted, bare = match.groups()
        if not PLACEHOLDER.fullmatch(quoted or bare) and not REFERENCE.fullmatch(bare or ""):
            return "literal credential"
    return None


def sensitive_name(path):
    parts = [part.lower() for part in path.split("/")]
    templates = {p for p in parts if any(fnmatch.fnmatch(p, t) for t in TEMPLATES)}
    return any(fnmatch.fnmatch(p, f) for p in parts if p not in templates for f in FORBIDDEN)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_lines():
    # Names are checked only for new (A/C/R) paths; content of every staged file is still scanned.
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACR", "-z")
    if any(map(sensitive_name, paths.decode("utf-8", errors="replace").split("\0"))):
        raise ValueError("sensitive filename added or renamed")
    patch = git(
        "diff", "--cached", "--no-ext-diff", "--no-textconv", "--unified=0", "--no-color"
    ).decode("utf-8", errors="replace")
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
        elif line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            yield line[1:]


def main():
    try:
        if len(sys.argv) > 2:
            raise ValueError("expected at most one commit message file")
        lines = (
            Path(sys.argv[1]).read_text(errors="replace").splitlines()
            if len(sys.argv) == 2
            else staged_lines()
        )
        for number, line in enumerate(lines, 1):
            label = check_line(line)
            if label:
                raise ValueError(f"{label} detected at scanned line {number}")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        # Do not render exceptions that might contain filenames or source text.
        detail = str(error) if type(error) is ValueError else "unable to read scan input"
        print(f"Secret guard: {detail}. Remove sensitive data before committing.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
