#!/usr/bin/env python3
"""Detect the PR opened by an AI-Factory run for a given issue.

Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.3). Extracts the
42-line inline bash block from
.github/workflows/claude-issue-to-pr.yml -> job implement -> step
"Detect Partial Success", preserving the false-positive guard that
forces the PR branch name or title to contain the ticket id or issue
reference before claiming a match.

The legacy bash flow is reproduced exactly:
    1. Build SEARCH_TERM = TICKET_ID else f"issue-{ISSUE_NUM}".
    2. gh pr list --state all --search "$SEARCH_TERM"
                  --json number,url,state,headRefName,title
    3. Take the first result.
    4. Reject (as false positive) if neither headRefName nor title
       contains TICKET_ID (case-insensitive) nor "issue-${N}"
       (case-insensitive).

Any gh invocation error is fatal (exit 1). A missing match is not an
error: the script exits 0 with pr_found=false.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any


def _run_gh(args: list[str]) -> str:
    """Run `gh` and return stdout. Raises CalledProcessError on failure."""
    executable = shutil.which("gh")
    if executable is None:
        raise FileNotFoundError("gh CLI not found in PATH")
    result = subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, output=result.stdout, stderr=result.stderr
        )
    return result.stdout


def _gh_pr_list(search_term: str) -> list[dict[str, Any]]:
    raw = _run_gh(
        [
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            search_term,
            "--json",
            "number,url,state,headRefName,title",
        ]
    )
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"gh pr list returned non-JSON: {raw!r}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"gh pr list returned non-array: {raw!r}")
    return parsed


def _matches_guard(pr: dict[str, Any], ticket_id: str | None, issue_number: int) -> bool:
    branch = (pr.get("headRefName") or "").lower()
    title = (pr.get("title") or "").lower()
    haystack = f"{branch} {title}"
    if ticket_id and ticket_id.lower() in haystack:
        return True
    if f"issue-{issue_number}" in haystack:
        return True
    return False


def find_pr(issue_number: int, ticket_id: str | None) -> dict[str, Any]:
    search_term = ticket_id if ticket_id else f"issue-{issue_number}"
    prs = _gh_pr_list(search_term)
    if not prs:
        return {"pr_found": False}
    first = prs[0]
    if not _matches_guard(first, ticket_id, issue_number):
        print(
            f"warning: PR #{first.get('number')} branch/title does not contain "
            f"{search_term} — treating as false positive",
            file=sys.stderr,
        )
        return {"pr_found": False}
    return {
        "pr_found": True,
        "pr_num": first.get("number"),
        "pr_url": first.get("url") or "",
        "pr_state": first.get("state") or "",
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Find the PR opened by an AI-Factory run for a given issue.",
    )
    p.add_argument(
        "--issue-number",
        required=True,
        type=int,
        help="GitHub issue number driving the AI-Factory run.",
    )
    p.add_argument(
        "--ticket-id",
        default=None,
        help="Linear ticket id (e.g. CAB-1234) if available — tightens the search.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if "GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ:
        print(
            "warning: neither GH_TOKEN nor GITHUB_TOKEN is set — "
            "gh may prompt or fail",
            file=sys.stderr,
        )
    try:
        result = find_pr(args.issue_number, args.ticket_id)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"error: gh failed with exit {exc.returncode}: {exc.stderr}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
