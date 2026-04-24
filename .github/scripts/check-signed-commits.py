#!/usr/bin/env python3
"""Verify signed commits policy (Gate 6A — warning only).

Classifies each commit as one of:
  - bot           : author is a bot or known service account (exempt)
  - grandfathered : human commit authored before the baseline (exempt)
  - signed        : human commit authored at/after baseline, GPG-verified
  - unsigned      : human commit authored at/after baseline, not verified

Only `unsigned` produces a ``::warning::`` annotation. The script NEVER
exits non-zero for policy violations — the surrounding job stays
warning-only under Gate 6A. It exits non-zero only for usage errors or
self-test failures.

Usage:
  check-signed-commits.py <sha1> [<sha2> ...] [--summary-file PATH]
      Evaluate the given commit SHAs (resolved via `git` in the current
      repo). If ``--summary-file`` is given, the markdown table is
      appended there (intended for ``$GITHUB_STEP_SUMMARY``); otherwise
      it is printed to stdout. Annotations are always printed to stdout.
  check-signed-commits.py --self-test
      Run the fixture suite. Exits 1 on any failure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import subprocess
import sys
from typing import NamedTuple

# Baseline: human commits authored strictly before this are grandfathered.
# Commits authored at or after this should be GPG-signed.
BASELINE = dt.datetime(2026, 4, 25, 0, 0, 0, tzinfo=dt.timezone.utc)

# Service accounts (non-"[bot]" identities) treated as bots. Derived from
# observed repo history (`git log --format='%an %ae' --all | sort -u`).
SERVICE_ACCOUNT_EMAILS = frozenset({
    "hegemon-worker@gostoa.dev",
})

_BOT_NAME_RE = re.compile(r"\[bot\]$")


class CommitInfo(NamedTuple):
    sha: str
    authored_at: dt.datetime
    author_name: str
    author_email: str
    signed: bool


def is_bot(name: str, email: str) -> bool:
    if _BOT_NAME_RE.search(name):
        return True
    if email in SERVICE_ACCOUNT_EMAILS:
        return True
    return False


def classify(info: CommitInfo, baseline: dt.datetime = BASELINE) -> str:
    if is_bot(info.author_name, info.author_email):
        return "bot"
    if info.authored_at < baseline:
        return "grandfathered"
    return "signed" if info.signed else "unsigned"


def _git_metadata(sha: str) -> tuple[dt.datetime, str, str]:
    out = subprocess.check_output(
        ["git", "log", "-1", "--format=%aI%x1f%an%x1f%ae", sha],
        text=True,
    ).rstrip("\n")
    parts = out.split("\x1f")
    if len(parts) != 3:
        raise RuntimeError(f"unexpected git log output for {sha}: {out!r}")
    iso, name, email = parts
    return dt.datetime.fromisoformat(iso), name, email


def _git_signed(sha: str) -> bool:
    rc = subprocess.call(
        ["git", "verify-commit", sha],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rc == 0


def inspect(sha: str) -> CommitInfo:
    authored_at, name, email = _git_metadata(sha)
    return CommitInfo(sha, authored_at, name, email, _git_signed(sha))


def render_summary(rows: list[tuple[CommitInfo, str]]) -> str:
    buf = io.StringIO()
    buf.write("## Commit Signature Verification\n\n")
    buf.write("| Commit | Author | Authored | Verdict |\n")
    buf.write("|--------|--------|----------|---------|\n")
    badge = {
        "bot": ":robot: Bot (exempt)",
        "grandfathered": ":clock1: Grandfathered",
        "signed": ":white_check_mark: Signed",
        "unsigned": ":warning: Unsigned",
    }
    counts = {"bot": 0, "grandfathered": 0, "signed": 0, "unsigned": 0}
    for info, verdict in rows:
        counts[verdict] += 1
        author = info.author_name.replace("|", "\\|")
        buf.write(
            f"| `{info.sha[:8]}` | {author} "
            f"| {info.authored_at.isoformat()} | {badge[verdict]} |\n"
        )
    total = sum(counts.values())
    buf.write(
        f"\n**{counts['unsigned']}/{total} post-baseline unsigned** "
        f"(bot={counts['bot']}, grandfathered={counts['grandfathered']}, "
        f"signed={counts['signed']})\n"
    )
    buf.write(f"\n_Baseline: human commits authored at or after {BASELINE.isoformat()} must be GPG-signed._\n")
    return buf.getvalue()


def evaluate(commits: list[str], summary_file: str | None = None) -> int:
    rows = [(info, classify(info)) for info in (inspect(sha) for sha in commits)]
    summary = render_summary(rows)
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    else:
        sys.stdout.write(summary)

    unsigned = [info for info, v in rows if v == "unsigned"]
    for info in unsigned:
        print(
            f"::warning::Unsigned post-baseline commit {info.sha[:8]} "
            f"by {info.author_name} <{info.author_email}> "
            f"at {info.authored_at.isoformat()}"
        )
    if unsigned:
        print(f"::warning::{len(unsigned)} post-baseline commit(s) not GPG-signed")
    return 0


# ---------------------------------------------------------------- self-test

_BASELINE_FIX = BASELINE  # fixtures use the live baseline to prevent drift

_FIXTURES = [
    # (label, CommitInfo, expected verdict)
    (
        "bot unsigned is exempt",
        CommitInfo(
            "aaaaaaaa",
            dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.timezone.utc),
            "dependabot[bot]",
            "49699333+dependabot[bot]@users.noreply.github.com",
            False,
        ),
        "bot",
    ),
    (
        "claude[bot] unsigned is exempt",
        CommitInfo(
            "bbbbbbbb",
            dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.timezone.utc),
            "claude[bot]",
            "209825114+claude[bot]@users.noreply.github.com",
            False,
        ),
        "bot",
    ),
    (
        "service account (hegemon) unsigned is exempt",
        CommitInfo(
            "cccccccc",
            dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.timezone.utc),
            "HEGEMON Worker (vmi3109794)",
            "hegemon-worker@gostoa.dev",
            False,
        ),
        "bot",
    ),
    (
        "human unsigned day before baseline is grandfathered",
        CommitInfo(
            "dddddddd",
            dt.datetime(2026, 4, 24, 23, 59, tzinfo=dt.timezone.utc),
            "Jane Dev",
            "jane@example.com",
            False,
        ),
        "grandfathered",
    ),
    (
        "human unsigned at baseline boundary is post-baseline (warning)",
        CommitInfo(
            "eeeeeeee",
            _BASELINE_FIX,
            "Jane Dev",
            "jane@example.com",
            False,
        ),
        "unsigned",
    ),
    (
        "human unsigned after baseline warns",
        CommitInfo(
            "ffffffff",
            dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.timezone.utc),
            "Jane Dev",
            "jane@example.com",
            False,
        ),
        "unsigned",
    ),
    (
        "human signed after baseline is ok",
        CommitInfo(
            "99999999",
            dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.timezone.utc),
            "Jane Dev",
            "jane@example.com",
            True,
        ),
        "signed",
    ),
    (
        "human signed before baseline is grandfathered (sig irrelevant)",
        CommitInfo(
            "88888888",
            dt.datetime(2026, 4, 24, 12, 0, tzinfo=dt.timezone.utc),
            "Jane Dev",
            "jane@example.com",
            True,
        ),
        "grandfathered",
    ),
]


def _self_test() -> int:
    failed = 0
    for label, info, expected in _FIXTURES:
        got = classify(info, _BASELINE_FIX)
        status = "PASS" if got == expected else "FAIL"
        print(f"{status} [{expected}]: {label} → {got}")
        if got != expected:
            failed += 1
    total = len(_FIXTURES)
    if failed:
        print(f"\n{failed}/{total} tests failed", file=sys.stderr)
        return 1
    print(f"\nAll {total} tests passed")
    return 0


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check-signed-commits.py",
        description="Gate 6A signed-commits policy (warning only).",
    )
    parser.add_argument("commits", nargs="*", help="commit SHAs to evaluate")
    parser.add_argument(
        "--summary-file",
        help="path to append the markdown summary to (e.g. $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run fixture suite"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.commits:
        parser.print_usage(sys.stderr)
        print("error: no commits given", file=sys.stderr)
        return 2
    return evaluate(args.commits, summary_file=args.summary_file)


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
