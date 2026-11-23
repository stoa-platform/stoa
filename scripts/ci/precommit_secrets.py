#!/usr/bin/env python3
"""Reject sensitive filenames and obvious secrets in staged additions, messages or ranges.

This local guard complements the full Gitleaks CI scan. Diagnostics never echo
matched content. Only explicit placeholders and variable references are exempt.

Modes:
  (no argument)  scan the staged diff (pre-commit hook).
  FILE           scan a commit message file (commit-msg hook), whatever its name.
  --range BASE HEAD [--allow-empty] [--direct]
                 scan the paths and lines added between the merge base of BASE and HEAD
                 (BASE itself with --direct) and HEAD, and the message of every commit in
                 BASE..HEAD. An empty commit range is an error unless --allow-empty is set.
                 A shallow repository is always an error: its history can be incomplete.
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
# Capability marker: lets a caller check that this copy of the script supports --range.
RANGE_MODE_SUPPORTED = True
RANGE_USAGE = "expected --range BASE HEAD [--allow-empty] [--direct]"
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # C0, DEL and C1
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
PATCH_FORMAT = ("--no-ext-diff", "--no-textconv", "--text", "--unified=0")
PATCH_FORMAT += ("--inter-hunk-context=0", "--no-color")
MESSAGE_FORMAT = ("--no-patch", "--encoding=UTF-8", "--no-show-signature", "--format=%B")


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


def object_id(detail, *args):
    """Run a git command that must print exactly one object id; fail with a fixed detail."""
    try:
        words = git(*args).decode("ascii", errors="replace").split()
    except subprocess.CalledProcessError:
        raise ValueError(detail) from None
    if len(words) != 1 or not OBJECT_ID.fullmatch(words[0]):
        raise ValueError(detail)
    return words[0]


def resolve_commit(revision):
    # Options, range expressions and control characters never reach git.
    if not revision or revision[0] == "-" or ".." in revision or CONTROL.search(revision):
        raise ValueError("invalid git revision")
    detail = "unable to resolve git revision"
    # The commit check applies to the resolved id, not to the input: appended to
    # "<rev>:<path>", a peel suffix would become part of the path and could name a tree.
    resolved = object_id(detail, "rev-parse", "--verify", "--quiet", revision)
    return object_id(detail, "rev-parse", "--verify", "--quiet", resolved + "^{commit}")


def added_lines(patch):
    """Yield (file index, new line number, text) for each added line of a git patch.

    Only a line feed ends a patch line, so a carriage return or another separator inside
    a file line can neither hide the rest of that line nor imitate a header. An empty line
    inside a hunk is a blank context line written without its prefix
    (diff.suppressBlankEmpty) and counts as one line.
    """
    file_index, number = 0, None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            file_index, number = file_index + 1, None
        elif line.startswith("@@ "):
            hunk = HUNK.match(line)
            if not hunk:
                raise ValueError("unexpected git diff output")
            number = int(hunk.group(1))
        elif number is not None and line[:1] in ("+", " ", ""):
            if line[:1] == "+":
                yield file_index, number, line[1:]
            number += 1


def range_findings(base, head, allow_empty=False, direct=False):
    """Return findings (rule label and position only) for the commit range BASE..HEAD."""
    base, head = resolve_commit(base), resolve_commit(head)
    # Past a shallow boundary git lists fewer commits for BASE..HEAD without any error.
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("shallow repository, full history is required")
    commits = git("rev-list", f"{base}..{head}", "--").decode("ascii", errors="replace").split()
    if not commits and not allow_empty:
        raise ValueError("empty commit range")
    # The merge base keeps changes made on BASE after the branch point out of the diff;
    # --direct compares with BASE itself, which also covers a branch moved backwards.
    tree = base if direct else object_id("unable to resolve merge base", "merge-base", base, head)
    # Both diffs are pinned against repository and user settings. --no-relative keeps paths
    # outside the current directory, --ignore-submodules=none lists every gitlink, and
    # --submodule=short shows a gitlink as one line, never as the submodule's own log or patch.
    span = ("--no-relative", "--ignore-submodules=none", "--submodule=short", tree, head, "--")
    findings = []
    paths = git("diff", "--name-only", "--diff-filter=ACR", "-z", *span)
    for index, path in enumerate(paths.decode("utf-8", errors="replace").split("\0"), 1):
        if sensitive_name(path):
            findings.append(f"sensitive filename added or renamed at diff path #{index}")
    # --text keeps paths that git or .gitattributes treat as binary in the scanned patch;
    # --inter-hunk-context=0 keeps the unchanged lines between two hunks out of it.
    patch = git("diff", *PATCH_FORMAT, *span)
    for index, number, line in added_lines(patch.decode("utf-8", errors="replace")):
        label = check_line(line)
        if label:
            findings.append(f"{label} detected in diff file #{index} at line {number}")
    for index, commit in enumerate(commits, 1):
        # The message is read as UTF-8 whatever i18n.logOutputEncoding says, without any
        # signature check output (log.showSignature). The trailing "--" keeps a worktree
        # file named like the commit out of the lookup.
        message = git("show", *MESSAGE_FORMAT, commit, "--")
        for number, line in enumerate(message.decode("utf-8", errors="replace").split("\n"), 1):
            label = check_line(line)
            if label:
                findings.append(
                    f"{label} detected in commit #{index} ({commit[:12]}) message at line {number}"
                )
    return findings


def range_main(base, head, *flags):
    try:
        if len(set(flags)) != len(flags) or not set(flags) <= {"--allow-empty", "--direct"}:
            raise ValueError(RANGE_USAGE)
        findings = range_findings(base, head, "--allow-empty" in flags, "--direct" in flags)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        # Same rule as below: only the fixed messages raised by this script are rendered.
        detail = str(error) if type(error) is ValueError else "unable to read scan input"
        print(f"Secret guard: {detail}. Range scan failed closed.", file=sys.stderr)
        return 1
    for finding in findings:
        print(f"Secret guard: {finding}. Remove sensitive data from the range.", file=sys.stderr)
    return 1 if findings else 0


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--range":
        return range_main(*sys.argv[2:])
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
