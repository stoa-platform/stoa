"""Tests for scripts/ci/wait_for_label.sh via pytest + subprocess.

Every test injects a fake `gh` binary on PATH and a fake `sleep` that
is a no-op, so the polling loop runs instantly.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "wait_for_label.sh"


def _run_script(
    args: list[str],
    tmp_path: Path,
    *,
    fake_gh_body: str,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Invoke wait_for_label.sh with a stubbed gh binary + no-op sleep."""
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            ATTEMPTS_FILE="${{FAKE_GH_ATTEMPTS:-/tmp/fake-gh-attempts}}"
            touch "$ATTEMPTS_FILE"
            echo "." >> "$ATTEMPTS_FILE"
            ATTEMPT=$(wc -l < "$ATTEMPTS_FILE" | tr -d ' ')
            if [ -n "${{FAKE_GH_LOG:-}}" ]; then
                printf '[%s] %s\\n' "$ATTEMPT" "$*" >> "$FAKE_GH_LOG"
            fi
            {fake_gh_body}
            """
        )
    )
    fake_gh.chmod(0o755)

    full_env = os.environ.copy()
    full_env["GH"] = str(fake_gh)
    full_env["SLEEP"] = "true"  # instant no-op
    full_env["FAKE_GH_ATTEMPTS"] = str(tmp_path / "attempts.log")
    if env:
        full_env.update(env)

    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )


def test_label_found_first_attempt(tmp_path):
    result = _run_script(
        ["42", "plan-validated", "5", "0"],
        tmp_path,
        fake_gh_body='''
        if [[ "$*" == *labels* ]]; then
            echo "plan-validated"
            exit 0
        fi
        exit 0
        ''',
    )
    assert result.returncode == 0
    assert "plan-validated found on issue 42" in result.stdout
    assert "validated=true" in result.stdout


def test_label_found_third_attempt(tmp_path):
    result = _run_script(
        ["42", "plan-validated", "5", "0"],
        tmp_path,
        fake_gh_body='''
        if [[ "$*" == *labels* ]]; then
            if [ "$ATTEMPT" -lt 3 ]; then
                echo "other-label"
            else
                echo "plan-validated"
            fi
            exit 0
        fi
        exit 0
        ''',
    )
    assert result.returncode == 0
    assert "validated=true" in result.stdout
    # Should have emitted at least one ::notice:: before succeeding
    assert "::notice::" in result.stdout


def test_timeout_when_label_never_appears(tmp_path):
    result = _run_script(
        ["42", "plan-validated", "3", "0"],
        tmp_path,
        fake_gh_body='echo "other-label"; exit 0',
    )
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "Timed out waiting for plan-validated" in result.stdout
    assert "validated=false" in result.stdout


def test_fallback_comment_pattern_triggers_success(tmp_path):
    # labels call returns empty; comments call returns length > 0
    result = _run_script(
        ["42", "plan-validated", "3", "0", "Plan Score"],
        tmp_path,
        fake_gh_body='''
        if [[ "$*" == *comments* ]]; then
            echo "1"
            exit 0
        fi
        exit 0  # labels path returns empty
        ''',
    )
    assert result.returncode == 0
    assert "fallback comment 'Plan Score' found" in result.stdout
    assert "validated=true" in result.stdout


def test_fallback_not_used_when_pattern_empty(tmp_path):
    # even with a matching comment payload, if no pattern is passed,
    # the fallback branch must not fire
    log = tmp_path / "calls.log"
    result = _run_script(
        ["42", "plan-validated", "2", "0"],
        tmp_path,
        fake_gh_body='echo "nothing-matches"; exit 0',
        env={"FAKE_GH_LOG": str(log)},
    )
    assert result.returncode == 1
    calls = log.read_text().splitlines()
    # Only 'issue view ... --json labels' calls, never '--json comments'
    assert all("comments" not in c for c in calls), calls


def test_gh_error_on_labels_does_not_abort(tmp_path):
    # A single failing gh call should not crash the loop; the label
    # stays undetected and we retry.
    result = _run_script(
        ["42", "plan-validated", "3", "0"],
        tmp_path,
        fake_gh_body='''
        if [ "$ATTEMPT" -eq 1 ]; then
            echo "gh boom" >&2
            exit 4
        fi
        if [[ "$*" == *labels* ]]; then
            echo "plan-validated"
            exit 0
        fi
        ''',
    )
    assert result.returncode == 0
    assert "validated=true" in result.stdout


def test_writes_to_github_output(tmp_path):
    github_output = tmp_path / "github_output.txt"
    github_output.write_text("")
    result = _run_script(
        ["42", "plan-validated", "2", "0"],
        tmp_path,
        fake_gh_body='echo "plan-validated"; exit 0',
        env={"GITHUB_OUTPUT": str(github_output)},
    )
    assert result.returncode == 0
    assert github_output.read_text().strip() == "validated=true"


def test_writes_validated_false_to_github_output_on_timeout(tmp_path):
    github_output = tmp_path / "out.txt"
    github_output.write_text("")
    result = _run_script(
        ["42", "plan-validated", "2", "0"],
        tmp_path,
        fake_gh_body='echo ""; exit 0',
        env={"GITHUB_OUTPUT": str(github_output)},
    )
    assert result.returncode == 1
    assert github_output.read_text().strip() == "validated=false"


def test_no_sleep_on_final_attempt(tmp_path):
    # If the loop ever slept AFTER the final attempt, we'd see more
    # calls than max-attempts. Mock gh to always fail and count calls.
    log = tmp_path / "calls.log"
    _run_script(
        ["42", "plan-validated", "4", "0"],
        tmp_path,
        fake_gh_body='echo ""; exit 0',
        env={"FAKE_GH_LOG": str(log)},
    )
    calls = log.read_text().splitlines()
    # Each attempt triggers exactly one --json labels call (no fallback
    # pattern specified). Exactly 4 attempts -> 4 calls.
    assert len(calls) == 4


def test_missing_args(tmp_path):
    result = _run_script([], tmp_path, fake_gh_body="exit 0")
    assert result.returncode == 2
    assert "usage" in result.stderr


def test_label_not_substring_matched(tmp_path):
    # Same strict matching as gh_helpers.has_label: "plan-validated-old"
    # must NOT count as "plan-validated".
    result = _run_script(
        ["42", "plan-validated", "2", "0"],
        tmp_path,
        fake_gh_body='echo "plan-validated-old"; exit 0',
    )
    assert result.returncode == 1
    assert "validated=false" in result.stdout
