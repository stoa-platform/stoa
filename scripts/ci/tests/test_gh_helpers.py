"""Shell-script tests for scripts/ci/gh_helpers.sh via pytest + subprocess.

Per decision K1 of the rewrite plan: when bats-core install is not
trivial in CI, bash helpers are covered via pytest driving bash as a
subprocess, with a fake `gh` binary injected on PATH.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "gh_helpers.sh"


def _run_bash(snippet: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a bash one-liner that sources gh_helpers.sh and executes `snippet`."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    script = f"set -uo pipefail; source '{SCRIPT}'\n{snippet}"
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=cwd,
        check=False,
    )


def _make_fake_gh(tmp_path: Path, behavior: str) -> Path:
    """Write a fake `gh` executable and return its path.

    `behavior` is a bash snippet that receives "$@" and writes the
    canned output (stdout/stderr) + exits with the required code.
    The fake also appends each invocation to $FAKE_GH_LOG if set.
    """
    gh = tmp_path / "gh"
    gh.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [ -n "${{FAKE_GH_LOG:-}}" ]; then
                printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
            fi
            {behavior}
            """
        )
    )
    gh.chmod(0o755)
    return gh


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CAB-1234 fix something", "CAB-1234"),
        ("a bunch of CAB-99 and CAB-7 later", "CAB-99"),
        ("no ticket here", ""),
        ("", ""),
        ("has-CAB-123inside", "CAB-123"),
        ("cab-123", ""),  # case-sensitive, like legacy bash
    ],
)
def test_extract_ticket_id(text, expected):
    result = _run_bash(
        f'printf "%s" "$(extract_ticket_id {text!r})"',
    )
    assert result.returncode == 0
    assert result.stdout == expected


def test_has_label_returns_0_when_present(tmp_path):
    gh = _make_fake_gh(
        tmp_path,
        'if [ "$4" = "--json" ]; then echo "council-validated"; echo "other"; exit 0; fi; exit 1',
    )
    result = _run_bash(
        'has_label 42 "council-validated"',
        env={"GH": str(gh)},
    )
    assert result.returncode == 0


def test_has_label_returns_1_when_absent(tmp_path):
    gh = _make_fake_gh(tmp_path, 'echo "other-label"; exit 0')
    result = _run_bash(
        'has_label 42 "council-validated"',
        env={"GH": str(gh)},
    )
    assert result.returncode == 1


def test_has_label_returns_1_on_gh_error(tmp_path):
    gh = _make_fake_gh(tmp_path, 'echo "boom" >&2; exit 4')
    result = _run_bash(
        'has_label 42 "council-validated"',
        env={"GH": str(gh)},
    )
    assert result.returncode == 1


def test_has_label_missing_args():
    result = _run_bash("has_label 42")
    assert result.returncode == 2
    assert "usage" in result.stderr


def test_has_label_fxq_handles_substrings(tmp_path):
    # Legacy bash uses `grep -q` which would match a substring like
    # "council-validated-old" as a match for "council-validated". The
    # extracted helper uses `grep -Fxq` (fixed, full line), which is
    # what we want. Verify strict matching.
    gh = _make_fake_gh(tmp_path, 'echo "council-validated-old"; exit 0')
    result = _run_bash(
        'has_label 42 "council-validated"',
        env={"GH": str(gh)},
    )
    assert result.returncode == 1


def test_ensure_label_calls_gh_once(tmp_path):
    log = tmp_path / "calls.log"
    gh = _make_fake_gh(tmp_path, "exit 0")
    result = _run_bash(
        'ensure_label "council-validated" "0e8a16" "Council OK"',
        env={"GH": str(gh), "FAKE_GH_LOG": str(log)},
    )
    assert result.returncode == 0
    calls = log.read_text().splitlines()
    assert len(calls) == 1
    assert "label create council-validated" in calls[0]
    assert "--force" in calls[0]
    assert "--color 0e8a16" in calls[0]


def test_ensure_label_swallows_gh_failure(tmp_path):
    gh = _make_fake_gh(tmp_path, 'echo "already exists" >&2; exit 1')
    result = _run_bash(
        'ensure_label "council-validated" "0e8a16" "desc"',
        env={"GH": str(gh)},
    )
    assert result.returncode == 0


def test_ensure_label_missing_args():
    result = _run_bash('ensure_label "name"')
    assert result.returncode == 2
    assert "usage" in result.stderr


def test_add_label_invokes_gh_correctly(tmp_path):
    log = tmp_path / "calls.log"
    gh = _make_fake_gh(tmp_path, "exit 0")
    result = _run_bash(
        'add_label 42 "council-validated"',
        env={"GH": str(gh), "FAKE_GH_LOG": str(log)},
    )
    assert result.returncode == 0
    call = log.read_text().strip()
    assert "issue edit 42" in call
    assert "--add-label council-validated" in call


def test_add_label_propagates_failure(tmp_path):
    gh = _make_fake_gh(tmp_path, 'echo "nope" >&2; exit 4')
    result = _run_bash(
        'add_label 42 "council-validated"',
        env={"GH": str(gh)},
    )
    assert result.returncode != 0


def test_add_label_missing_args():
    result = _run_bash("add_label 42")
    assert result.returncode == 2


def test_direct_execution_prints_usage():
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "source this file" in result.stdout.lower()
