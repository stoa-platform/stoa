"""Regression test for CAB-2083 (Security P0-02).

The literal `Parzival@2026!` was committed as a fallback in five files of the
public repository. This test prevents the pattern from being re-introduced:
any consumer that wants the credential must read it from the environment.

If this test fails, remove the literal and source the value from
`PARZIVAL_PASSWORD` instead (GitHub Secrets in CI, local .env otherwise).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_LITERAL = "Parzival@2026!"


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a git checkout — skip when packaged",
)
def test_parzival_password_is_never_hardcoded() -> None:
    """Fail if the Parzival password literal is committed anywhere."""
    # `git ls-files | xargs grep` is faster than a Python walk and honors
    # .gitignore automatically, so vendored copies in node_modules, venv,
    # target, etc. don't leak into the scan.
    result = subprocess.run(  # noqa: S603 — fixed args, no user input
        ["git", "grep", "-n", "--fixed-strings", FORBIDDEN_LITERAL],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    # This regression test file legitimately mentions the literal — filter it
    # out. Anything else is a regression.
    offenders = [
        line
        for line in result.stdout.splitlines()
        if not line.startswith("control-plane-api/tests/test_regression_cab_2083_")
    ]

    assert offenders == [], (
        "CAB-2083 regression: the Parzival password literal reappeared in:\n"
        + "\n".join(offenders)
        + "\n\nRead it from the PARZIVAL_PASSWORD env var instead."
    )
