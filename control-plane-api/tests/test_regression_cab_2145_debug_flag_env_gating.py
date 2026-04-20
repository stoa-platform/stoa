"""Regression tests for CAB-2145 (Security MEGA CAB-2079 — debug flag env gating).

Before the fix:
- `LOG_DEBUG_AUTH_TOKENS`, `LOG_DEBUG_AUTH_PAYLOAD`, `LOG_DEBUG_AUTH_HEADERS`,
  `LOG_DEBUG_HTTP_BODY`, and `LOG_DEBUG_HTTP_HEADERS` were plain booleans on
  `Settings`. Nothing stopped them being flipped to `True` in a prod Helm
  override — in which case live JWT bearer tokens and request bodies ended up
  in stdout logs and OpenSearch indices.
- The config-drift audit (CAB-2140 / PR #2448) verified prod has them all
  False today, but there was no mechanism to keep them that way.

After the fix:
- A Pydantic model validator fails fast at app startup when `ENVIRONMENT
  == "production"` and ANY flag in `SENSITIVE_DEBUG_FLAGS_IN_PROD` is `True`.
  The traceback names the flag(s) so the operator can find the Helm override
  quickly.
- In dev/staging the validator emits a loud warning but does not crash, so
  local debugging workflows keep working.
"""

# regression for CAB-2079
import logging

import pytest

from src.config import SENSITIVE_DEBUG_FLAGS_IN_PROD, Settings


class TestProductionRejectsDebugFlags:
    """Every sensitive flag, combined with ENVIRONMENT=production, must raise."""

    @pytest.mark.parametrize("flag", SENSITIVE_DEBUG_FLAGS_IN_PROD)
    def test_flag_true_in_prod_raises(self, flag: str):
        with pytest.raises(ValueError) as exc:
            Settings(ENVIRONMENT="production", **{flag: True})
        # The flag name must appear in the error so the operator knows what to flip.
        assert flag in str(exc.value)

    def test_all_flags_false_in_prod_boots(self):
        # Canary: the validator must not be overly aggressive and reject a clean prod boot.
        s = Settings(ENVIRONMENT="production")
        assert s.ENVIRONMENT == "production"
        for flag in SENSITIVE_DEBUG_FLAGS_IN_PROD:
            assert getattr(s, flag) is False

    def test_multiple_flags_all_reported(self):
        with pytest.raises(ValueError) as exc:
            Settings(
                ENVIRONMENT="production",
                LOG_DEBUG_AUTH_TOKENS=True,
                LOG_DEBUG_HTTP_BODY=True,
            )
        msg = str(exc.value)
        assert "LOG_DEBUG_AUTH_TOKENS" in msg
        assert "LOG_DEBUG_HTTP_BODY" in msg


class TestDevAndStagingOnlyWarn:
    """Dev and staging should log a warning, never crash."""

    @pytest.mark.parametrize("env", ["dev", "staging"])
    def test_flag_true_in_non_prod_does_not_raise(self, env: str, caplog):
        caplog.set_level(logging.WARNING)
        s = Settings(ENVIRONMENT=env, LOG_DEBUG_AUTH_TOKENS=True)
        assert env == s.ENVIRONMENT
        assert s.LOG_DEBUG_AUTH_TOKENS is True
        # Operator-visible warning must mention the flag.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("LOG_DEBUG_AUTH_TOKENS" in r.getMessage() for r in warnings)

    def test_silent_when_no_flag_set(self, caplog):
        caplog.set_level(logging.WARNING)
        Settings(ENVIRONMENT="dev")
        warnings = [r for r in caplog.records if "LOG_DEBUG" in r.getMessage()]
        assert warnings == []


class TestSensitiveListCoverage:
    """The sensitive list must include the auth-token + payload + body flags
    that actually leak credential-grade data in prod. Guard against someone
    renaming a field and forgetting to update the allow-list."""

    def test_auth_tokens_flag_is_covered(self):
        assert "LOG_DEBUG_AUTH_TOKENS" in SENSITIVE_DEBUG_FLAGS_IN_PROD

    def test_auth_payload_flag_is_covered(self):
        assert "LOG_DEBUG_AUTH_PAYLOAD" in SENSITIVE_DEBUG_FLAGS_IN_PROD

    def test_http_body_flag_is_covered(self):
        assert "LOG_DEBUG_HTTP_BODY" in SENSITIVE_DEBUG_FLAGS_IN_PROD

    def test_all_listed_flags_exist_on_settings(self):
        s = Settings()
        for flag in SENSITIVE_DEBUG_FLAGS_IN_PROD:
            assert hasattr(s, flag), f"SENSITIVE_DEBUG_FLAGS_IN_PROD references {flag}, which is not a Settings field"
