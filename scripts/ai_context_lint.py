#!/usr/bin/env python3
"""AI context lint — block regressions of AI-facing project context.

Scans the AI-facing contract files (CLAUDE.md, AGENTS.md, README.md) and the
.claude/ subtree for stale markers that must not reappear. The goal is to
prevent an LLM-driven edit from reintroducing retired architecture or paths
that no longer exist.

Exit status:
  0 — no blocking finding (warnings may still be printed to stderr)
  1 — one or more blocking findings
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TOP_LEVEL_FILES = ("CLAUDE.md", "AGENTS.md", "README.md")
CLAUDE_SUBTREE_GLOB = ".claude/**/*.md"

# Stale stack-version markers — always blocked (current stack: React 19, Go 1.25).
# They never belong in an active context file; a genuinely historical prompt
# must declare itself via a top-of-file banner (see HISTORICAL_BANNER_RE).
STALE_VERSION_MARKERS = (
    ("React 18", "stale React 18 reference"),
    ("Go 1.22", "stale Go 1.22 reference"),
)

# Universally toxic markers — blocked wherever they appear, no exceptions.
UNIVERSAL_MARKERS = (
    ("MCP GW (Py)", "retired Python MCP Gateway reference"),
    (".Codex/", "nonexistent .Codex/ path"),
)

# Standalone `.Codex` token (not `.CodexFoo`).
CODEX_STANDALONE = re.compile(r"\.Codex(?![A-Za-z0-9_])")

# Static "Next = ADR-<N>" reference — forbidden because ADR numbers are owned
# by stoa-docs and the index is the source of truth.
NEXT_ADR_STATIC = re.compile(r"Next\s*=\s*ADR-\d+")

# Contextual tokens: blocked unless neighbored by a historical keyword.
MCP_GATEWAY_TOKEN = re.compile(r"\bmcp-gateway\b")
CLAUDE_RULES_TOKEN = re.compile(r"\.claude/rules\b")

HISTORICAL_KEYWORDS = (
    "historical", "history", "legacy", "retired", "deprecated",
    "archived", "superseded", "replaced", "old",
    "ancien", "historique", "retiré", "retire",
    "déprécié", "deprecie", "remplacé", "remplace",
)
HISTORICAL_RE = re.compile(
    r"(?i)\b(?:" + "|".join(re.escape(k) for k in HISTORICAL_KEYWORDS) + r")\b"
)

# Top-of-file banner: a file that declares itself historical in its first few
# lines (e.g. `> **Historical prompt (retired):** ...`) gets whole-file
# tolerance for mcp-gateway / .claude/rules mentions. The banner must explicitly
# classify the file as a preserved historical artifact, not merely mention the
# word `historical` in passing.
HISTORICAL_BANNER_RE = re.compile(
    r"(?im)^\s*>?\s*(?:\*\*)?historical\s+"
    r"(?:prompt|note|file|snapshot|example|reference)\b"
)
BANNER_SCAN_LINES = 5

CONTEXT_WINDOW = 2

# Advisory thresholds.
AGENTS_LINE_LIMIT = 80
CLAUDE_LINE_LIMIT = 250

REACT_VERSION = re.compile(r"React\s+(\d+)")
GO_VERSION = re.compile(r"Go\s+(\d+\.\d+)")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _collect_files() -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for name in TOP_LEVEL_FILES:
        p = REPO_ROOT / name
        if p.is_file() and p not in seen:
            seen.add(p)
            ordered.append(p)
    for p in sorted(REPO_ROOT.glob(CLAUDE_SUBTREE_GLOB)):
        if p.is_file() and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _context_window(lines: list[str], idx: int, width: int) -> str:
    start = max(0, idx - width)
    end = min(len(lines), idx + width + 1)
    return " ".join(lines[start:end])


def _has_historical_banner(lines: list[str]) -> bool:
    """True if the file declares itself historical in its first few lines."""
    head = "\n".join(lines[:BANNER_SCAN_LINES])
    return bool(HISTORICAL_BANNER_RE.search(head))


def _check_stale_markers(path: Path, lines: list[str], errors: list[str]) -> None:
    rel = _rel(path)
    banner = _has_historical_banner(lines)
    for lineno, line in enumerate(lines, start=1):
        for marker, reason in UNIVERSAL_MARKERS:
            if marker in line:
                errors.append(f"{rel}:{lineno}: {reason}")
        if CODEX_STANDALONE.search(line) and ".Codex/" not in line:
            errors.append(f"{rel}:{lineno}: nonexistent .Codex reference")
        if NEXT_ADR_STATIC.search(line):
            errors.append(f"{rel}:{lineno}: static Next ADR reference")
        if not banner:
            for marker, reason in STALE_VERSION_MARKERS:
                if marker in line:
                    errors.append(f"{rel}:{lineno}: {reason}")


def _check_contextual(path: Path, lines: list[str], errors: list[str]) -> None:
    """Flag active mcp-gateway / .claude/rules mentions without historical framing."""
    rel = _rel(path)
    if _has_historical_banner(lines):
        return
    for idx, line in enumerate(lines):
        lineno = idx + 1
        ctx = _context_window(lines, idx, CONTEXT_WINDOW)
        tolerated = bool(HISTORICAL_RE.search(ctx))
        if MCP_GATEWAY_TOKEN.search(line) and not tolerated:
            errors.append(
                f"{rel}:{lineno}: active mcp-gateway reference "
                "(retired Feb 2026 — mark as historical/retired/superseded)"
            )
        if CLAUDE_RULES_TOKEN.search(line) and not tolerated:
            errors.append(
                f"{rel}:{lineno}: active .claude/rules reference "
                "(superseded by CLAUDE.md hierarchy)"
            )


def _check_agents_references_claude(errors: list[str]) -> None:
    agents = REPO_ROOT / "AGENTS.md"
    if not agents.is_file():
        return
    text = agents.read_text(encoding="utf-8")
    if "CLAUDE.md" not in text:
        errors.append(
            f"{_rel(agents)}: must reference CLAUDE.md as the canonical contract"
        )


def _advisory_line_counts(warnings: list[str]) -> None:
    claude = REPO_ROOT / "CLAUDE.md"
    agents = REPO_ROOT / "AGENTS.md"
    for path, limit in ((claude, CLAUDE_LINE_LIMIT), (agents, AGENTS_LINE_LIMIT)):
        if not path.is_file():
            continue
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n > limit:
            warnings.append(
                f"{_rel(path)}: {n} lines exceeds advisory limit {limit}"
            )


def _advisory_version_drift(warnings: list[str]) -> None:
    claude = REPO_ROOT / "CLAUDE.md"
    readme = REPO_ROOT / "README.md"
    if not (claude.is_file() and readme.is_file()):
        return
    claude_txt = claude.read_text(encoding="utf-8")
    readme_txt = readme.read_text(encoding="utf-8")
    for label, regex in (("React", REACT_VERSION), ("Go", GO_VERSION)):
        c_vers = {m.group(1) for m in regex.finditer(claude_txt)}
        r_vers = {m.group(1) for m in regex.finditer(readme_txt)}
        if c_vers and r_vers and c_vers != r_vers:
            warnings.append(
                f"README.md: {label} version mismatch with CLAUDE.md "
                f"(CLAUDE={sorted(c_vers)}, README={sorted(r_vers)})"
            )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    files = _collect_files()

    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        _check_stale_markers(path, lines, errors)
        _check_contextual(path, lines, errors)

    _check_agents_references_claude(errors)
    _advisory_line_counts(warnings)
    _advisory_version_drift(warnings)

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    if errors:
        print("AI context lint failed:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1

    print("AI context lint passed.")
    print(f"Checked {len(files)} files.")
    print("No stale AI context markers.")
    print("No active retired gateway references.")
    print("No static Next ADR references.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
