"""CAB-2199 / INFRA-1a S5 — regression guards for tightened Pydantic validators.

Two changes covered:
- ``LOG_FORMAT: Literal["json", "text"]`` (was bare ``str``) — typos like
  ``LOG_FORMAT=jsno`` now fail fast at boot instead of silently degrading.
- ``ENVIRONMENT`` validator: surgical ``prod → production`` mapping
  (gateway uses ``prod``, cp-api stores the canonical ``production``).
  Christophe arbitrage 2026-04-29 §3.4 nuance: emit ``logger.info`` line at
  boot when normalization is applied so an operator sees the rewrite
  explicitly.

Tests:
- LOG_FORMAT: invalid value rejected by Literal narrowing.
- LOG_FORMAT: both ``json`` and ``text`` accepted.
- ENVIRONMENT: ``prod`` → ``production`` with INFO log emitted.
- ENVIRONMENT: ``production``, ``dev``, ``Staging`` pass through (no
  case-fold of unrelated values — BH-8 mitigation).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Each test in tmp cwd with no .env + cleared ENVIRONMENT/LOG_FORMAT env vars."""
    monkeypatch.chdir(tmp_path)
    for key in ("ENVIRONMENT", "LOG_FORMAT", "GITHUB_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_log_format_literal_rejects_invalid():
    """Typo like ``LOG_FORMAT=yaml`` fails fast — Literal narrowing."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(LOG_FORMAT="yaml")  # type: ignore[arg-type]
    msg = str(exc_info.value)
    assert "LOG_FORMAT" in msg


def test_log_format_accepts_valid_values():
    """Both ``json`` and ``text`` are valid (the documented set)."""
    s = Settings(LOG_FORMAT="json")
    assert s.LOG_FORMAT == "json"

    s = Settings(LOG_FORMAT="text")
    assert s.LOG_FORMAT == "text"


def test_environment_prod_normalized_to_production(caplog):
    """``ENVIRONMENT=prod`` → canonical ``production`` (gateway uses 'prod')."""
    with caplog.at_level("INFO", logger="src.config"):
        s = Settings(ENVIRONMENT="prod", GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == "production"


def test_environment_prod_emits_normalization_info_log(caplog):
    """§3.4 ops-signal nuance: emit a ``logger.info`` line whenever
    normalization is applied so the operator inspecting the boot logs sees
    the rewrite explicitly."""
    with caplog.at_level("INFO", logger="src.config"):
        Settings(ENVIRONMENT="prod", GITHUB_TOKEN="fake")
    matching = [
        r for r in caplog.records
        if "ENVIRONMENT normalized" in r.message and "'prod' → 'production'" in r.message
    ]
    assert matching, f"expected normalization log line, got records: {[r.message for r in caplog.records]}"
    # The log line cites CAB-2199 / INFRA-1a for traceability.
    assert "CAB-2199" in matching[0].message


def test_environment_production_no_normalization_log(caplog):
    """Setting ``ENVIRONMENT=production`` directly (no normalization needed)
    must NOT emit the §3.4 ops-signal log line."""
    with caplog.at_level("INFO", logger="src.config"):
        Settings(ENVIRONMENT="production", GITHUB_TOKEN="fake")
    matching = [r for r in caplog.records if "ENVIRONMENT normalized" in r.message]
    assert not matching, "log line fired unexpectedly for non-normalized value"


def test_environment_other_values_pass_through_no_case_fold():
    """``Staging``, ``PRODUCTION``, ``dev`` pass through with caller spelling
    preserved — BH-8 mitigation: avoid silent case-fold of unrelated values."""
    s = Settings(ENVIRONMENT="Staging")
    assert s.ENVIRONMENT == "Staging"  # case preserved

    s = Settings(ENVIRONMENT="dev")
    assert s.ENVIRONMENT == "dev"

    # PRODUCTION (uppercase) is NOT mapped to production — only the bare
    # `prod` token is. PRODUCTION will fail the prod-gate elsewhere because
    # `is_production` checks `== "production"` literal — but THIS validator
    # does not silently rewrite it.
    s = Settings(ENVIRONMENT="PRODUCTION")
    assert s.ENVIRONMENT == "PRODUCTION"  # caller spelling preserved


def test_environment_whitespace_stripped():
    """Leading/trailing whitespace is stripped (K8s-mounted values with
    trailing newlines survive — same pattern as ``_normalize_git_provider``)."""
    s = Settings(ENVIRONMENT="   dev   ")
    assert s.ENVIRONMENT == "dev"

    s = Settings(ENVIRONMENT="\nprod\t", GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == "production"
