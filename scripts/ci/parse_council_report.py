#!/usr/bin/env python3
"""Parse a Council report emitted by anthropics/claude-code-action.

Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.1). Consolidates the
score/mode/estimate extraction duplicated across 4 inline bash blocks
in .github/workflows/claude-issue-to-pr.yml (check-fast, sync-linear-s1,
sync-linear-s2, slack-council).

Parsing strategy (in order):
    1. Concatenate assistant.content[].text from execution-file.
    2. Try a fenced ```json ... ``` block containing a "score" key
       (structured contract — new pattern the Council prompt may emit).
    3. Fallback to the legacy regex patterns that the bash workflow
       currently relies on: "Council Score: X.XX/10" for s1 and
       "Plan Score: X.XX/10" for s2 (with generic Score fallback).
    4. If still empty and --fallback-comment is provided, re-run 2-3
       on the markdown comment body.

Verdict is derived from score: >=8.0 go, >=6.0 fix, else redo.

Emits a single-line JSON document on stdout. Exits 0 on success (even
if fields end up null, unless --strict). Writes diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_MODE_EXPLICIT_RE = re.compile(
    r"ship\s*/\s*show\s*/\s*ask\s*:?\s*(ship|show|ask)",
    re.IGNORECASE,
)
_MODE_CLASSIFICATION_RE = re.compile(
    r"classification\s*:?\s*(ship|show|ask)", re.IGNORECASE
)
_ESTIMATE_PATTERNS = (
    re.compile(r"estimate\s*:?\s*(\d+)\s*pts?", re.IGNORECASE),
    re.compile(r"\((\d+)\s*pts?\)", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*pts?\b", re.IGNORECASE),
)
_LOC_PATTERNS = (
    re.compile(r"total\s*:?\s*~?(\d+)\s*LOC", re.IGNORECASE),
    re.compile(r"(?:estimated\s+loc|loc)\s*:?\s*~?(\d+)", re.IGNORECASE),
    re.compile(r"~(\d+)\s*LOC", re.IGNORECASE),
)


def _concat_assistant_text(execution_data: Any) -> str:
    """Extract assistant.content[].text concatenated with newlines.

    Mirrors the jq used by the legacy bash step:
        jq -r '[.[] | select(.type == "assistant")
                     | .message.content[]?
                     | select(.type == "text") | .text] | join("\\n")'
    """
    if not isinstance(execution_data, list):
        return ""
    parts: list[str] = []
    for turn in execution_data:
        if not isinstance(turn, dict) or turn.get("type") != "assistant":
            continue
        message = turn.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            continue
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                text = chunk.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts)


def _try_structured_json(text: str) -> dict[str, Any] | None:
    """Find a fenced JSON block containing a 'score' key."""
    for match in _FENCED_JSON_RE.finditer(text):
        raw = match.group(1)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "score" in parsed:
            return parsed
    return None


def _extract_score_regex(text: str, stage: str) -> float | None:
    """Replicate the bash grep patterns exactly.

    For s1: first "(Council )?Score: X/10".
    For s2: first "Plan Score: X/10", else last generic "Score: X/10"
    (the bash uses tail -1 for its generic fallback).
    """
    if stage == "s1":
        for pattern in (
            r"Council\s+Score\s*:?\s*([0-9]+\.?[0-9]*)/10",
            r"Score\s*:?\s*([0-9]+\.?[0-9]*)/10",
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None

    m = re.search(
        r"Plan\s+Score\s*:?\s*([0-9]+\.?[0-9]*)/10",
        text,
        re.IGNORECASE,
    )
    if m:
        return float(m.group(1))
    matches = list(re.finditer(r"Score\s*:?\s*([0-9]+\.?[0-9]*)/10", text, re.IGNORECASE))
    if matches:
        return float(matches[-1].group(1))
    return None


def _extract_mode(text: str) -> str:
    m = _MODE_EXPLICIT_RE.search(text)
    if m:
        return m.group(1).lower()
    m = _MODE_CLASSIFICATION_RE.search(text)
    if m:
        return m.group(1).lower()
    return "ask"


def _extract_estimate_points(text: str) -> int:
    for rx in _ESTIMATE_PATTERNS:
        m = rx.search(text)
        if m:
            try:
                value = int(m.group(1))
                if 1 <= value <= 99:
                    return value
            except ValueError:
                continue
    for rx in _LOC_PATTERNS:
        m = rx.search(text)
        if m:
            try:
                loc = int(m.group(1))
            except ValueError:
                continue
            if loc <= 100:
                return 3
            if loc <= 300:
                return 5
            return 8
    return 0


def _derive_verdict(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 8.0:
        return "go"
    if score >= 6.0:
        return "fix"
    return "redo"


def _coerce_verdict(value: Any) -> str | None:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("go", "fix", "redo"):
            return lowered
    return None


def _coerce_mode(value: Any) -> str | None:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("ship", "show", "ask"):
            return lowered
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_text(text: str, stage: str, *, source_hint: str) -> dict[str, Any]:
    """Return a normalized result from a text body.

    `source_hint` is used when the structured JSON is absent: it indicates
    whether we fell back on regex of the execution file or of the
    fallback comment.
    """
    structured = _try_structured_json(text)
    if structured is not None:
        score = _coerce_float(structured.get("score"))
        verdict = _coerce_verdict(structured.get("verdict")) or _derive_verdict(score)
        mode = _coerce_mode(structured.get("mode")) or _extract_mode(text)
        estimate = _coerce_int(structured.get("estimate_points"))
        if estimate is None:
            estimate = _extract_estimate_points(text)
        return {
            "score": score,
            "verdict": verdict,
            "mode": mode,
            "estimate_points": estimate,
            "source": "structured_json",
        }

    score = _extract_score_regex(text, stage)
    return {
        "score": score,
        "verdict": _derive_verdict(score),
        "mode": _extract_mode(text),
        "estimate_points": _extract_estimate_points(text),
        "source": source_hint,
    }


def _read_execution_text(path: Path) -> tuple[str, bool]:
    """Return (text, file_existed). Empty string + False if missing."""
    if not path.exists():
        return "", False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: could not parse execution file {path}: {exc}", file=sys.stderr)
        return "", True
    return _concat_assistant_text(data), True


def run(
    execution_file: Path,
    stage: str,
    fallback_comment: Path | None,
    strict: bool,
) -> tuple[int, dict[str, Any]]:
    text, exec_existed = _read_execution_text(execution_file)

    if text:
        result = parse_text(text, stage, source_hint="regex")
    else:
        result = {
            "score": None,
            "verdict": None,
            "mode": "ask",
            "estimate_points": 0,
            "source": "regex",
        }

    needs_fallback = (
        fallback_comment is not None
        and (not exec_existed or result.get("score") is None)
    )
    if needs_fallback:
        assert fallback_comment is not None  # for type checker
        if fallback_comment.exists():
            try:
                body = fallback_comment.read_text(encoding="utf-8")
            except OSError as exc:
                print(
                    f"warning: could not read fallback comment {fallback_comment}: {exc}",
                    file=sys.stderr,
                )
                body = ""
            if body:
                result = parse_text(body, stage, source_hint="fallback")

    if strict and result.get("score") is None:
        print("strict mode: no score extracted", file=sys.stderr)
        return 1, result

    if not exec_existed and fallback_comment is None:
        return 1, result

    return 0, result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Parse a Council report to extract score/verdict/mode/estimate.",
    )
    p.add_argument(
        "--execution-file",
        required=True,
        type=Path,
        help="Path to claude-execution-output.json.",
    )
    p.add_argument(
        "--stage",
        required=True,
        choices=("s1", "s2"),
        help="Council stage (s1 = pertinence, s2 = plan).",
    )
    p.add_argument(
        "--fallback-comment",
        type=Path,
        default=None,
        help="Optional markdown comment file to parse if execution file is missing.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if no score could be extracted.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code, result = run(
        args.execution_file,
        args.stage,
        args.fallback_comment,
        args.strict,
    )
    print(json.dumps(result, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
