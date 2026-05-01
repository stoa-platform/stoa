"""Regression tests for CAB-2199 ENVIRONMENT fail-closed validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Run with no ambient .env or ENVIRONMENT/GITHUB_TOKEN leakage."""
    monkeypatch.chdir(tmp_path)
    for key in ("ENVIRONMENT", "GITHUB_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_regression_cab_2199_environment_case_variation_triggers_prod_auth_gate():
    """Case variations of prod/production must not bypass production gates."""
    for spelling in ("Prod", "PROD", "PRODUCTION", "Production"):
        with pytest.raises(ValidationError, match="STOA_DISABLE_AUTH"):
            Settings(ENVIRONMENT=spelling, STOA_DISABLE_AUTH=True, GITHUB_TOKEN="fake")


def test_regression_cab_2199_environment_unknown_value_rejected():
    """Unknown ENVIRONMENT values must fail closed instead of becoming non-prod."""
    with pytest.raises(ValidationError, match="not recognized"):
        Settings(ENVIRONMENT="produciton", GITHUB_TOKEN="fake")
