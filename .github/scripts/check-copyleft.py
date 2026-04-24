#!/usr/bin/env python3
"""Evaluate SPDX license expressions against an allow/deny policy.

Replaces the previous substring heuristic that flagged `BSD-3-Clause OR
GPL-2.0-only` as copyleft. Grammar follows the SPDX License Expression
spec (AND/OR/WITH/parens). An expression is acceptable iff at least one
OR-branch's AND-terms are all in the allow set.

Usage:
  check-copyleft.py <spdx.json>   prints `name: license` per copyleft finding
  check-copyleft.py --self-test   runs the fixture suite
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional

ALLOWED = {
    "0BSD", "APACHE-1.0", "APACHE-1.1", "APACHE-2.0", "ARTISTIC-2.0",
    "BOOST-1.0", "BSD-1-CLAUSE", "BSD-2-CLAUSE", "BSD-3-CLAUSE",
    "BSD-3-CLAUSE-CLEAR", "BSL-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC0-1.0",
    "ISC", "MIT", "MPL-2.0", "PSF-2.0", "PYTHON-2.0", "UNLICENSE",
    "WTFPL", "X11", "ZLIB",
}

DENIED = {
    "AGPL-1.0", "AGPL-1.0-ONLY", "AGPL-1.0-OR-LATER",
    "AGPL-3.0", "AGPL-3.0-ONLY", "AGPL-3.0-OR-LATER",
    "CPAL-1.0", "EUPL-1.0", "EUPL-1.1", "EUPL-1.2",
    "GPL-2.0", "GPL-2.0-ONLY", "GPL-2.0-OR-LATER",
    "GPL-3.0", "GPL-3.0-ONLY", "GPL-3.0-OR-LATER",
    "LGPL-2.0", "LGPL-2.0-ONLY", "LGPL-2.0-OR-LATER",
    "LGPL-2.1", "LGPL-2.1-ONLY", "LGPL-2.1-OR-LATER",
    "LGPL-3.0", "LGPL-3.0-ONLY", "LGPL-3.0-OR-LATER",
    "OSL-3.0", "SSPL-1.0",
}

_TOKEN_RE = re.compile(r"\(|\)|[A-Za-z0-9.\-+]+")
_SENTINEL_UNKNOWN = {"", "NOASSERTION", "NONE"}


class _ParseError(Exception):
    pass


def _tokenize(expr: str) -> list[str]:
    return _TOKEN_RE.findall(expr.strip())


def _parse_or(tokens: list[str], pos: int) -> tuple[dict, int]:
    node, pos = _parse_and(tokens, pos)
    terms = [node]
    while pos < len(tokens) and tokens[pos].upper() == "OR":
        nxt, pos = _parse_and(tokens, pos + 1)
        terms.append(nxt)
    return (node if len(terms) == 1 else {"type": "or", "children": terms}), pos


def _parse_and(tokens: list[str], pos: int) -> tuple[dict, int]:
    node, pos = _parse_atom(tokens, pos)
    terms = [node]
    while pos < len(tokens) and tokens[pos].upper() == "AND":
        nxt, pos = _parse_atom(tokens, pos + 1)
        terms.append(nxt)
    return (node if len(terms) == 1 else {"type": "and", "children": terms}), pos


def _parse_atom(tokens: list[str], pos: int) -> tuple[dict, int]:
    if pos >= len(tokens):
        raise _ParseError("unexpected end of expression")
    tok = tokens[pos]
    if tok == "(":
        inner, pos = _parse_or(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise _ParseError("unclosed parenthesis")
        return inner, pos + 1
    if tok.upper() in {"AND", "OR", "WITH", ")"}:
        raise _ParseError(f"unexpected operator {tok!r}")
    pos += 1
    if pos < len(tokens) and tokens[pos].upper() == "WITH":
        if pos + 1 >= len(tokens):
            raise _ParseError("expected exception after WITH")
        pos += 2  # consume WITH + exception id; treat expression as the base license
    return {"type": "license", "id": tok}, pos


def parse_expression(expr: str) -> dict:
    tokens = _tokenize(expr)
    if not tokens:
        raise _ParseError("empty expression")
    node, consumed = _parse_or(tokens, 0)
    if consumed != len(tokens):
        raise _ParseError(f"trailing tokens: {tokens[consumed:]}")
    return node


def is_acceptable(node: dict, allowed: set[str], denied: set[str]) -> Optional[bool]:
    """True = at least one allowed path, False = must include denied, None = indeterminate."""
    t = node["type"]
    if t == "license":
        uid = node["id"].upper()
        if uid in allowed:
            return True
        if uid in denied:
            return False
        return None
    children = [is_acceptable(c, allowed, denied) for c in node["children"]]
    if t == "or":
        if any(r is True for r in children):
            return True
        return False if all(r is False for r in children) else None
    if t == "and":
        if any(r is False for r in children):
            return False
        return True if all(r is True for r in children) else None
    return None


def classify(expr: str) -> str:
    """Return one of: 'allowed', 'copyleft', 'unknown'."""
    if not expr or expr.strip().upper() in _SENTINEL_UNKNOWN:
        return "unknown"
    try:
        node = parse_expression(expr)
    except _ParseError:
        return "unknown"
    verdict = is_acceptable(node, ALLOWED, DENIED)
    return {True: "allowed", False: "copyleft"}.get(verdict, "unknown")


def scan_spdx(path: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    copyleft: list[tuple[str, str]] = []
    unknown: list[tuple[str, str]] = []
    for pkg in data.get("packages", []):
        name = pkg.get("name") or "?"
        expr = (pkg.get("licenseDeclared") or pkg.get("licenseConcluded") or "").strip()
        verdict = classify(expr)
        if verdict == "copyleft":
            copyleft.append((name, expr))
        elif verdict == "unknown" and expr and expr.upper() not in _SENTINEL_UNKNOWN:
            unknown.append((name, expr))
    return copyleft, unknown


_FIXTURES = [
    # (expected, expression)
    ("allowed", "MIT"),
    ("allowed", "Apache-2.0"),
    ("allowed", "BSD-3-Clause"),
    ("allowed", "ISC"),
    ("allowed", "BSD-3-Clause OR GPL-2.0-only"),
    ("allowed", "MIT OR GPL-3.0-only"),
    ("allowed", "Apache-2.0 OR LGPL-2.1-only"),
    ("allowed", "(MIT OR BSD-3-Clause) AND Apache-2.0"),
    ("allowed", "Apache-2.0 WITH LLVM-exception"),
    ("allowed", "MIT OR (GPL-3.0-only AND AGPL-3.0-only)"),
    ("copyleft", "GPL-2.0-only"),
    ("copyleft", "GPL-3.0-only"),
    ("copyleft", "AGPL-3.0-only"),
    ("copyleft", "LGPL-3.0-only"),
    ("copyleft", "SSPL-1.0"),
    ("copyleft", "EUPL-1.2"),
    ("copyleft", "MIT AND GPL-3.0-only"),
    ("copyleft", "Apache-2.0 AND AGPL-3.0-only"),
    ("copyleft", "(GPL-3.0-only OR AGPL-3.0-only) AND MIT"),
    ("unknown", ""),
    ("unknown", "NOASSERTION"),
    ("unknown", "NONE"),
    ("unknown", "UNKNOWN"),
    ("unknown", "SEE LICENSE IN LICENSE"),
    ("unknown", "custom-license"),
    ("unknown", "MIT AND UnknownLicense-1.0"),
]


def _self_test() -> int:
    failed = 0
    for expected, expr in _FIXTURES:
        got = classify(expr)
        status = "PASS" if got == expected else "FAIL"
        print(f"{status} [{expected}]: {expr!r} → {got}")
        if got != expected:
            failed += 1
    total = len(_FIXTURES)
    if failed:
        print(f"\n{failed}/{total} tests failed", file=sys.stderr)
        return 1
    print(f"\nAll {total} tests passed")
    return 0


def _main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    if len(argv) < 2:
        print("usage: check-copyleft.py <spdx.json> | --self-test", file=sys.stderr)
        return 2
    copyleft, unknown = scan_spdx(argv[1])
    for name, expr in copyleft:
        print(f"{name}: {expr}")
    if unknown:
        print(
            f"::notice::{len(unknown)} package(s) with indeterminate license expressions (manual review)",
            file=sys.stderr,
        )
        for name, expr in unknown[:20]:
            print(f"  - {name}: {expr}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
