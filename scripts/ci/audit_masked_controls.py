"""Advisory scan for CI checks that can look green without running.

Looks through GitHub Actions workflows for motifs that hide a missed or
failed check: a literal or expression ``continue-on-error``, a command whose
failure is swallowed with ``|| true``, a ``::warning::`` that does not
``exit 1``, and a step ``if`` that skips a probe when DNS, a skip output, or
a deploy kill-switch is unset.

The process always exits 0. It is not a merge gate and no workflow calls it.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CONTINUE_TRUE = re.compile(r"continue-on-error:\s*true\b")
CONTINUE_EXPR = re.compile(r"continue-on-error:\s*\$\{\{")
SWALLOW = re.compile(r"\|\|\s*true\b")
# Cleanup, search, and tooling fallbacks. A failed grep is not a skipped test.
CLEANUP = re.compile(
    r"(grep|kubectl|kill\b|rm\b|docker\b|systemctl|chmod|ls\b|"
    r"\bgit\b|\bgh\b|sccache|cargo install)\b",
    re.IGNORECASE,
)
# Smoke DNS, the health-smoke resolver, and the deploy/scan kill switches.
# Other `outputs.skip` values (ticket extractors) are ordinary early exits.
CONDITIONAL = re.compile(
    r"resolves|resolve\.outputs\.skip|GITOPS_DEPLOY_ENABLED|DISABLE_"
)
RUN_BLOCK = re.compile(r"^(\s*)run:\s*[>|]\s*$")
RUN_INLINE = re.compile(r"^\s*run:\s*(\S.*)$")
IF_LINE = re.compile(r"^\s*if:\s*(.+)$")
WARNING = "::warning::"
EXIT_FAIL = re.compile(r"\bexit\s+1\b")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scan_line(path: str, line: str, number: int) -> list[Finding]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []
    found: list[Finding] = []
    if CONTINUE_TRUE.search(stripped):
        found.append(Finding(path, number, "continue-on-error", stripped))
    elif CONTINUE_EXPR.search(stripped):
        found.append(Finding(path, number, "continue-on-error", stripped))
    if SWALLOW.search(stripped) and not CLEANUP.search(stripped):
        found.append(Finding(path, number, "swallowed-command", stripped))
    match = IF_LINE.match(line)
    if match and CONDITIONAL.search(match.group(1)):
        found.append(Finding(path, number, "conditional-skip", stripped))
    return found


def _warning_finding(path: str, block: list[str], start: int) -> Finding | None:
    code = [line for line in block if not line.strip().startswith("#")]
    body = "\n".join(code)
    if WARNING not in body or EXIT_FAIL.search(body):
        return None
    for offset, line in enumerate(block):
        if WARNING in line:
            return Finding(
                path,
                start + offset,
                "warning-without-failure",
                line.strip()[:160],
            )
    return None


def scan_text(path: str, text: str) -> list[Finding]:
    """Return masked-control motifs in one workflow file."""
    lines = text.splitlines()
    findings: list[Finding] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        number = index + 1
        if RUN_BLOCK.match(line):
            base = _indent(line)
            block: list[str] = []
            index += 1
            while index < total:
                nxt = lines[index]
                if nxt.strip() and _indent(nxt) <= base:
                    break
                block.append(nxt)
                index += 1
            for offset, block_line in enumerate(block):
                findings.extend(_scan_line(path, block_line, number + 1 + offset))
            warning = _warning_finding(path, block, number + 1)
            if warning:
                findings.append(warning)
            continue
        findings.extend(_scan_line(path, line, number))
        inline = RUN_INLINE.match(line)
        if inline and inline.group(1) not in {">", "|"}:
            warning = _warning_finding(path, [inline.group(1)], number)
            if warning:
                findings.append(warning)
        index += 1
    return findings


def scan_paths(roots: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.yml"))
        files.extend([] if root.is_file() else sorted(root.rglob("*.yaml")))
        for path in files:
            findings.extend(scan_text(str(path), path.read_text(encoding="utf-8")))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".github/workflows")],
        help="workflow files or directories (default: .github/workflows)",
    )
    args = parser.parse_args(argv)
    findings = scan_paths(args.paths)
    if not findings:
        print("no masked-control motifs")
    else:
        for finding in findings:
            print(finding.format())
    return 0


if __name__ == "__main__":
    sys.exit(main())
