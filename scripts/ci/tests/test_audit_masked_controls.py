"""The masked-control scanner flags a hidden check and ignores a real one."""

from __future__ import annotations

from pathlib import Path

import audit_masked_controls as scanner

MASKED = """\
name: Masked
on: push
jobs:
  probe:
    continue-on-error: true
    steps:
      - name: Audit
        run: pip-audit -r requirements.txt || true
      - name: Prod smoke
        if: steps.dns.outputs.resolves == 'true'
        run: python smoke.py
      - name: Verify
        run: |
          echo "::warning::Endpoint not healthy after 300s"
"""

HEALTHY = """\
name: Healthy
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Unit tests
        if: github.event_name == 'push'
        run: pytest -q
      - name: Enforce signatures
        continue-on-error: false
        run: python check_signatures.py
      - name: Diagnostics
        if: failure()
        run: |
          kubectl describe pod app || true
          grep -c '^+' diff.txt || true
      - name: Fail closed
        run: |
          echo "::warning::disk low"
          exit 1
"""


def test_masked_workflow_is_detected() -> None:
    findings = scanner.scan_text("masked.yml", MASKED)
    kinds = {item.kind for item in findings}
    assert kinds == {
        "continue-on-error",
        "swallowed-command",
        "conditional-skip",
        "warning-without-failure",
    }
    assert any("pip-audit" in item.detail for item in findings)


def test_healthy_workflow_is_ignored() -> None:
    assert scanner.scan_text("healthy.yml", HEALTHY) == []


def test_conditional_continue_on_error_is_detected() -> None:
    text = "jobs:\n  e2e:\n    continue-on-error: ${{ github.event_name == 'schedule' }}\n"
    findings = scanner.scan_text("e2e.yml", text)
    assert len(findings) == 1
    assert findings[0].kind == "continue-on-error"


def test_main_exits_zero(tmp_path: Path, capsys) -> None:
    (tmp_path / "masked.yml").write_text(MASKED, encoding="utf-8")
    assert scanner.main([str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "continue-on-error" in output
    assert "pip-audit" in output
