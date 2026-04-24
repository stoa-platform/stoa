#!/usr/bin/env python3
"""Map a Council score to a Linear label name.

Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.4). Extracted from the
duplicated score→label mapping inline in
.github/workflows/claude-issue-to-pr.yml (council-validate and
plan-validate Sync-to-Linear steps).

Thresholds (preserved from legacy bash):
    score >= 8.0 -> go
    score >= 6.0 -> fix
    else         -> redo

Example:
    $ python3 map_score_to_label.py --score 8.2 --namespace ticket
    council:ticket-go
"""

from __future__ import annotations

import argparse
import sys


def map_score(score: float, namespace: str) -> str:
    if namespace not in ("ticket", "plan"):
        raise ValueError(f"namespace must be 'ticket' or 'plan', got {namespace!r}")
    if score >= 8.0:
        verdict = "go"
    elif score >= 6.0:
        verdict = "fix"
    else:
        verdict = "redo"
    return f"council:{namespace}-{verdict}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Map a Council score to a Linear label name.",
    )
    p.add_argument("--score", required=True, help="Council score (float, 0.0-10.0).")
    p.add_argument(
        "--namespace",
        required=True,
        choices=("ticket", "plan"),
        help="Label namespace.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        score = float(args.score)
    except ValueError:
        print(f"invalid score: {args.score!r}", file=sys.stderr)
        return 1
    print(map_score(score, args.namespace))
    return 0


if __name__ == "__main__":
    sys.exit(main())
