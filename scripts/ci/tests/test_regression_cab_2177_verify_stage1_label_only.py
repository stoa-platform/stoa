"""Regression tests for CAB-2177.

Pre-fix: the inline `Verify Stage 1 Council` step in
`.github/workflows/claude-issue-to-pr.yml` had a comment-fallback
that scanned every issue comment for "Council Score" with no
freshness guard. Any stale Council comment — including one from a
verdict-gated run that did NOT apply the `council-validated` label,
or one left behind after a deliberate label removal — satisfied the
gate and let Stage 2 proceed against stale evidence.

Surfaced during the post-merge §H.2 Smoke 4 attempt for CI-1
Phase 2d (run 24953872143 on issue #2570): the issue had no
`council-validated` label but its 2026-04-25T23:57:02Z comment
from the CAB-2175 pre-fix run satisfied the fallback. Stage 2
ran for real, applying `plan-validated` against a negative-smoke
issue.

Post-fix: the comment-fallback is removed. The `council-validated`
label is the single source of truth, mirroring CAB-2175's
freshness pattern in `council-run`.

Tests target `scripts/ci/verify_stage1.sh` with subprocess + a
stubbed `gh` binary on PATH (same harness as
`test_wait_for_label.py`).
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "verify_stage1.sh"


def _run_script(
    args: list[str],
    tmp_path: Path,
    *,
    fake_gh_body: str,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Invoke verify_stage1.sh with a stubbed gh binary.

    Logs every gh invocation's argv to ``$FAKE_GH_LOG`` if set, so
    tests can assert the script never fetches comments.
    """
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [ -n "${{FAKE_GH_LOG:-}}" ]; then
                printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
            fi
            {fake_gh_body}
            """
        )
    )
    fake_gh.chmod(0o755)

    full_env = os.environ.copy()
    full_env["GH"] = str(fake_gh)
    if env:
        full_env.update(env)

    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )


def test_label_present_validates(tmp_path):
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='echo "council-validated"; exit 0',
    )
    assert result.returncode == 0
    assert "validated=true" in result.stdout
    assert "Stage 1 confirmed via council-validated label" in result.stdout


def test_label_absent_does_not_validate_and_never_reads_comments(tmp_path):
    # CAB-2177 regression: an issue with NO `council-validated`
    # label must NOT validate, regardless of any prior "Council
    # Score" comment in its history. The script must never fetch
    # comments — proven by the absence of `comments` in the gh
    # call log.
    log = tmp_path / "calls.log"
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='echo ""; exit 0',
        env={"FAKE_GH_LOG": str(log)},
    )
    assert result.returncode == 0
    assert "validated=false" in result.stdout
    calls = log.read_text().splitlines()
    assert calls, "expected at least one gh invocation (the labels lookup)"
    assert all("comments" not in c for c in calls), (
        f"verify_stage1 must not fetch comments — got: {calls}"
    )


def test_substring_label_does_not_match(tmp_path):
    # `council-validated-old` must NOT count as `council-validated`.
    # Mirrors the strict `grep -Fxq` exact-match used by
    # `wait_for_label.sh` (Phase 2c parity).
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='echo "council-validated-old"; exit 0',
    )
    assert result.returncode == 0
    assert "validated=false" in result.stdout


def test_writes_to_github_output(tmp_path):
    github_output = tmp_path / "out.txt"
    github_output.write_text("")
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='printf "bug\\ncouncil-validated\\nfeature\\n"; exit 0',
        env={"GITHUB_OUTPUT": str(github_output)},
    )
    assert result.returncode == 0
    assert github_output.read_text().strip() == "validated=true"


def test_writes_validated_false_to_github_output_when_absent(tmp_path):
    github_output = tmp_path / "out.txt"
    github_output.write_text("")
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='echo ""; exit 0',
        env={"GITHUB_OUTPUT": str(github_output)},
    )
    assert result.returncode == 0
    assert github_output.read_text().strip() == "validated=false"


def test_gh_failure_fails_closed(tmp_path):
    # gh exiting non-zero (auth issue, network, etc.) must NOT
    # bubble up as Stage 1 valid. Output is validated=false.
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='echo "boom" >&2; exit 4',
    )
    assert result.returncode == 0
    assert "validated=false" in result.stdout


def test_missing_arg(tmp_path):
    result = _run_script([], tmp_path, fake_gh_body="exit 0")
    assert result.returncode == 2
    assert "usage" in result.stderr


def test_council_validated_among_other_labels_validates(tmp_path):
    # Real issues carry multiple labels; the council-validated entry
    # must be detected on its own line via grep -Fxq.
    result = _run_script(
        ["2570"],
        tmp_path,
        fake_gh_body='printf "claude-implement\\ntype:infra\\ncouncil-validated\\n"; exit 0',
    )
    assert result.returncode == 0
    assert "validated=true" in result.stdout
