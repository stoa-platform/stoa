"""Tests for environment_guard (CAB-1291)"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.auth.environment_guard import ENVIRONMENT_MODES, require_writable_environment


def _make_user(roles=None):
    user = MagicMock()
    user.roles = roles or []
    user.id = "user-1"
    user.username = "alice"
    return user


class TestEnvironmentModes:
    def test_dev_is_full(self):
        assert ENVIRONMENT_MODES["dev"] == "full"

    def test_staging_is_full(self):
        assert ENVIRONMENT_MODES["staging"] == "full"

    def test_prod_is_read_only(self):
        assert ENVIRONMENT_MODES["prod"] == "read-only"


class TestRequireWritableEnvironment:
    def test_no_environment(self):
        user = _make_user()
        result = require_writable_environment(environment=None, user=user)
        assert result is user

    def test_dev_allowed(self):
        user = _make_user(roles=["viewer"])
        result = require_writable_environment(environment="dev", user=user)
        assert result is user

    def test_staging_allowed(self):
        user = _make_user(roles=["viewer"])
        result = require_writable_environment(environment="staging", user=user)
        assert result is user

    def test_prod_blocked_for_viewer(self):
        user = _make_user(roles=["viewer"])
        # Suppress structlog-style kwargs warning that uses keyword args
        with patch("src.auth.environment_guard.logger"):
            with pytest.raises(HTTPException) as exc_info:
                require_writable_environment(environment="prod", user=user)
            assert exc_info.value.status_code == 403
            assert "read-only" in exc_info.value.detail

    def test_prod_allowed_for_cpi_admin(self):
        user = _make_user(roles=["cpi-admin"])
        result = require_writable_environment(environment="prod", user=user)
        assert result is user

    def test_unknown_environment_defaults_to_full(self):
        user = _make_user(roles=["viewer"])
        result = require_writable_environment(environment="custom-env", user=user)
        assert result is user
