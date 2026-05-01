"""CAB-2199 / INFRA-1a S5 + Phase 3-A — regression guards for tightened Pydantic validators.

Two changes covered:
- ``LOG_FORMAT: Literal["json", "text"]`` (was bare ``str``) — typos like
  ``LOG_FORMAT=jsno`` now fail fast at boot instead of silently degrading.
- ``ENVIRONMENT`` validator: **fail-closed alias map** (Phase 3-A
  upgrade of the Phase 2 surgical normalize). Whitespace-strip +
  casefold + lookup in the alias map; unknown values raise. Replaces
  the Phase 2 partial-fix that mapped only the bare lowercase ``prod``
  token and let `PROD`/`Prod`/typos silently bypass the four
  ``== "production"`` security gates downstream.

Tests:
- LOG_FORMAT: invalid value rejected by Literal narrowing.
- LOG_FORMAT: both ``json`` and ``text`` accepted.
- ENVIRONMENT: ``prod`` → ``production`` with INFO log emitted.
- ENVIRONMENT: case-insensitive accept (`PROD`, `Prod`, `Staging`,
  `Development` all map to a canonical form).
- ENVIRONMENT: unknown value (`produciton`, `live`, `on-prem-prod`)
  rejected with a clear error message.
- ENVIRONMENT: whitespace stripped.
- Prod gate (`_gate_auth_bypass_in_prod`) fires on case variations
  — regression guard for the Phase 3-A bypass fix (covers BH-INFRA1a-001
  scenario: `STOA_DISABLE_AUTH=true` + `ENVIRONMENT=Prod` must raise).
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


def test_environment_prod_normalized_to_production():
    """``ENVIRONMENT=prod`` → canonical ``production`` (gateway uses 'prod')."""
    s = Settings(ENVIRONMENT="prod", GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == "production"


def test_environment_prod_emits_normalization_info_log(caplog):
    """Phase 3-A ops-signal: emit a ``logger.info`` line whenever
    normalization is applied so the operator inspecting the boot logs
    sees the rewrite explicitly."""
    with caplog.at_level("INFO", logger="src.config"):
        Settings(ENVIRONMENT="prod", GITHUB_TOKEN="fake")
    matching = [
        r for r in caplog.records
        if "ENVIRONMENT normalized" in r.message and "'prod'" in r.message and "'production'" in r.message
    ]
    assert matching, f"expected normalization log line, got records: {[r.message for r in caplog.records]}"
    # The log line cites CAB-2199 for traceability.
    assert "CAB-2199" in matching[0].message


def test_environment_production_no_normalization_log(caplog):
    """Setting ``ENVIRONMENT=production`` directly (no normalization needed)
    must NOT emit the ops-signal log line."""
    with caplog.at_level("INFO", logger="src.config"):
        Settings(ENVIRONMENT="production", GITHUB_TOKEN="fake")
    matching = [r for r in caplog.records if "ENVIRONMENT normalized" in r.message]
    assert not matching, "log line fired unexpectedly for non-normalized value"


@pytest.mark.parametrize(
    "value,expected_canonical",
    [
        ("PROD", "production"),
        ("Prod", "production"),
        ("PRODUCTION", "production"),
        ("Production", "production"),
        ("Staging", "staging"),
        ("STAGING", "staging"),
        ("Development", "dev"),
        ("DEV", "dev"),
        ("Test", "test"),
    ],
)
def test_environment_case_insensitive_mapping(value, expected_canonical):
    """Phase 3-A — case-insensitive accept for documented values.

    Replaces the Phase 2 BH-8-mitigation behavior where any non-`prod`
    spelling preserved caller case and silently fell through the
    ``== "production"`` security gates.
    """
    s = Settings(ENVIRONMENT=value, GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == expected_canonical


@pytest.mark.parametrize(
    "value",
    ["produciton", "live", "on-prem-prod", "PROD-EU", "qa", ""],
)
def test_environment_unknown_value_rejected(value):
    """Phase 3-A — fail-closed: unknown ENVIRONMENT values raise at boot.

    Covers the BH-INFRA1a-001 typo bypass: `produciton` / `live` /
    `on-prem-prod` must NEVER silently fall through the prod gates.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT=value, GITHUB_TOKEN="fake")
    msg = str(exc_info.value)
    assert "ENVIRONMENT" in msg
    assert "not recognized" in msg


def test_environment_whitespace_stripped():
    """Leading/trailing whitespace is stripped (K8s-mounted values with
    trailing newlines survive — same pattern as ``_normalize_git_provider``)."""
    s = Settings(ENVIRONMENT="   dev   ", GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == "dev"

    s = Settings(ENVIRONMENT="\nprod\t", GITHUB_TOKEN="fake")
    assert s.ENVIRONMENT == "production"


def test_prod_gate_fires_on_case_variations():
    """Phase 3-A regression guard for BH-INFRA1a-001 — case variations
    of ``ENVIRONMENT=prod``/`production` MUST trigger the prod gates.

    Pre-Phase 3-A, ``Settings(ENVIRONMENT="Prod", STOA_DISABLE_AUTH=True)``
    booted silently because the validator preserved caller case and the
    auth-bypass gate literal-checked ``ENVIRONMENT == "production"``.
    Post Phase 3-A, the validator normalizes the value first, so the
    gate sees the canonical ``production`` and refuses boot.
    """
    for spelling in ("Prod", "PROD", "PRODUCTION", "Production"):
        with pytest.raises(ValidationError, match="STOA_DISABLE_AUTH"):
            Settings(ENVIRONMENT=spelling, STOA_DISABLE_AUTH=True, GITHUB_TOKEN="fake")
