"""Regression guards for CP-1 C.2 (token leak in subprocess argv).

Previously, ``clone_repo`` injected the provider PAT into the HTTPS URL
passed to ``git clone``, making it visible via ``ps`` / ``/proc/PID/cmdline``
and capturing in container log scrapers. The fix routes credentials via
GIT_ASKPASS + environment vars; argv carries only the plain HTTPS URL.

These tests pin four invariants:
  1. Subprocess argv never contains the token.
  2. Subprocess env forces all git trace variables to "0" and disables
     interactive prompting.
  3. The ASKPASS helper is cleaned up on both success and failure.
  4. Exception messages raised from failed clones never echo the raw token.

Plus the defense-in-depth logging filter:
  5. Standard provider PAT formats are redacted in log records.
  6. Benign strings that merely contain a prefix are left alone.

regression for CP-1 C.2
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from src.config import GitHubConfig, GitLabConfig, GitProviderConfig
from src.core.secret_redactor import SecretRedactor, redact_secrets
from src.services.git_credentials import askpass_env, redact_token
from src.services.git_service import GitLabService
from src.services.github_service import GitHubService

_GITLAB_TOKEN = "glpat-abcdefghijklmnopqrst1234"
_GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _make_process(returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    """Build a mock for ``asyncio.create_subprocess_exec``'s return value."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(b"", stderr))
    return proc


def _patched_git_settings(provider: str, token: str) -> GitProviderConfig:
    """Construct a settings object with an in-memory token."""
    if provider == "gitlab":
        return GitProviderConfig(
            provider="gitlab",
            gitlab=GitLabConfig(
                url="https://gitlab.com",
                token=SecretStr(token),
                project_id="1",
                webhook_secret=SecretStr("whsec"),
            ),
        )
    return GitProviderConfig(
        provider="github",
        github=GitHubConfig(
            token=SecretStr(token),
            org="org",
            catalog_repo="catalog",
            webhook_secret=SecretStr("whsec"),
        ),
    )


class TestPatchedGitSettingsFixture:
    """CAB-1889 CP-2 H-1: guard against the silent-kwarg-drop regression.

    Before CP-2, ``_patched_git_settings`` passed ``catalog_project_id=``
    as a kwarg to ``GitHubConfig``, which is a read-only ``@property``.
    Pydantic's default ``extra="ignore"`` silently discarded it and the
    fixture ended up using the production defaults — invisible to every
    test in this file that relies on the helper. CP-2 fixes the fixture
    to populate the real fields and activates ``extra="forbid"`` (see
    ``test_git_provider.py``) so a future typo raises instead of drifting.
    """

    def test_github_fixture_uses_requested_org_and_catalog_repo(self):
        cfg = _patched_git_settings("github", _GITHUB_TOKEN)
        assert cfg.provider == "github"
        assert cfg.github.org == "org"
        assert cfg.github.catalog_repo == "catalog"
        assert cfg.github.catalog_project_id == "org/catalog"


# ──────────────────────────────────────────────────────────────────
# 1. Subprocess argv must not contain the token
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clone_repo_gitlab_no_token_in_argv(tmp_path):
    svc = GitLabService()
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env", {})
        return _make_process(returncode=0)

    settings_patch = _patched_git_settings("gitlab", _GITLAB_TOKEN)
    with (
        patch("src.services.git_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        await svc.clone_repo("https://gitlab.com/foo/bar.git")

    for arg in captured["args"]:
        assert _GITLAB_TOKEN not in str(arg), (
            f"token leaked to argv via {arg!r}"
        )


@pytest.mark.asyncio
async def test_clone_repo_github_no_token_in_argv(tmp_path):
    svc = GitHubService()
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env", {})
        return _make_process(returncode=0)

    settings_patch = _patched_git_settings("github", _GITHUB_TOKEN)
    with (
        patch("src.services.github_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        await svc.clone_repo("https://github.com/foo/bar.git")

    for arg in captured["args"]:
        assert _GITHUB_TOKEN not in str(arg), (
            f"token leaked to argv via {arg!r}"
        )


# ──────────────────────────────────────────────────────────────────
# 2. Subprocess env forces trace vars and terminal-prompt to "0"
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clone_repo_sets_trace_env_zero(tmp_path):
    svc = GitLabService()
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _make_process(returncode=0)

    settings_patch = _patched_git_settings("gitlab", _GITLAB_TOKEN)
    with (
        patch("src.services.git_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        await svc.clone_repo("https://gitlab.com/foo/bar.git")

    env = captured["env"]
    assert env["GIT_TRACE"] == "0"
    assert env["GIT_CURL_VERBOSE"] == "0"
    assert env["GIT_TRACE_CURL"] == "0"
    assert env["GIT_TRACE_PACKET"] == "0"
    assert env["GIT_TRACE_SETUP"] == "0"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    # ASKPASS helper path is present; token is NOT in the env key set
    # (only in STOA_GIT_PASSWORD value, which is intended).
    assert "GIT_ASKPASS" in env
    assert env["STOA_GIT_USERNAME"] == "oauth2"
    assert env["STOA_GIT_PASSWORD"] == _GITLAB_TOKEN


# ──────────────────────────────────────────────────────────────────
# 3. ASKPASS helper cleanup on both success and failure
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clone_repo_askpass_helper_cleanup_on_success(tmp_path):
    svc = GitLabService()
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["helper_path"] = kwargs["env"]["GIT_ASKPASS"]
        # Helper must exist DURING the subprocess call.
        assert Path(captured["helper_path"]).exists()
        return _make_process(returncode=0)

    settings_patch = _patched_git_settings("gitlab", _GITLAB_TOKEN)
    with (
        patch("src.services.git_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        await svc.clone_repo("https://gitlab.com/foo/bar.git")

    assert not Path(captured["helper_path"]).exists(), (
        "helper must be deleted after successful clone"
    )


@pytest.mark.asyncio
async def test_clone_repo_askpass_helper_cleanup_on_failure(tmp_path):
    svc = GitLabService()
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["helper_path"] = kwargs["env"]["GIT_ASKPASS"]
        return _make_process(returncode=128, stderr=b"fatal: authentication failed")

    settings_patch = _patched_git_settings("gitlab", _GITLAB_TOKEN)
    with (
        patch("src.services.git_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        with pytest.raises(RuntimeError):
            await svc.clone_repo("https://gitlab.com/foo/bar.git")

    assert not Path(captured["helper_path"]).exists(), (
        "helper must be deleted even when clone fails"
    )


# ──────────────────────────────────────────────────────────────────
# 4. Failed-clone exceptions never echo the raw token
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clone_repo_failure_exception_does_not_leak_token(tmp_path):
    """If stderr echoes the authenticated URL (misconfig, trace override,
    etc.), the exception message must redact the token before raising.
    """
    svc = GitLabService()
    leaky_stderr = (
        f"fatal: unable to access 'https://oauth2:{_GITLAB_TOKEN}@gitlab.com/foo/bar.git'"
    ).encode()

    async def fake_exec(*args, **kwargs):
        return _make_process(returncode=128, stderr=leaky_stderr)

    settings_patch = _patched_git_settings("gitlab", _GITLAB_TOKEN)
    with (
        patch("src.services.git_service.settings") as mock_settings,
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        patch("tempfile.mkdtemp", return_value=str(tmp_path)),
    ):
        mock_settings.git = settings_patch
        with pytest.raises(RuntimeError) as exc:
            await svc.clone_repo("https://gitlab.com/foo/bar.git")

    assert _GITLAB_TOKEN not in str(exc.value), (
        f"token leaked in exception: {exc.value}"
    )
    assert "***REDACTED***" in str(exc.value)


# ──────────────────────────────────────────────────────────────────
# ASKPASS helper dispatches username vs password correctly
# ──────────────────────────────────────────────────────────────────


def test_askpass_helper_replies_username_and_password_correctly(tmp_path):
    """Run the helper as git would: once per prompt type, capture stdout.

    Verifies the shell case statement dispatches Username / Password /
    fallback correctly. ``askpass_env`` yields the env dict; we extract
    the helper path and invoke it directly.
    """
    with askpass_env(username="x-access-token", password=_GITHUB_TOKEN) as env:
        helper = env["GIT_ASKPASS"]
        assert Path(helper).exists()
        # Env must carry the username + password for the helper to read.
        child_env = {**os.environ, **env}
        u_prompt = subprocess.run(  # noqa: S603 — helper is our own trusted script
            [helper, "Username for 'https://github.com':"],
            env=child_env, capture_output=True, check=True,
        )
        p_prompt = subprocess.run(  # noqa: S603 — helper is our own trusted script
            [helper, "Password for 'https://x-access-token@github.com':"],
            env=child_env, capture_output=True, check=True,
        )
        fallback = subprocess.run(  # noqa: S603 — helper is our own trusted script
            [helper, "Some other prompt:"],
            env=child_env, capture_output=True, check=True,
        )

    assert u_prompt.stdout == b"x-access-token"
    assert p_prompt.stdout == _GITHUB_TOKEN.encode()
    # Conservative fallback returns the password.
    assert fallback.stdout == _GITHUB_TOKEN.encode()


# ──────────────────────────────────────────────────────────────────
# Logging filter redaction
# ──────────────────────────────────────────────────────────────────


def test_logging_filter_redacts_gitlab_pat():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="failure: glpat-abcdefghijklmnopqrst1234", args=(), exc_info=None,
    )
    SecretRedactor().filter(record)
    assert "glpat-abcdefghijklmnopqrst1234" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_logging_filter_redacts_github_classic_pat():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="failure: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", args=(), exc_info=None,
    )
    SecretRedactor().filter(record)
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_logging_filter_redacts_github_finegrained_pat():
    fine = "github_pat_11ABCD_" + "x" * 70
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg=f"failure: {fine}", args=(), exc_info=None,
    )
    SecretRedactor().filter(record)
    assert fine not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_logging_filter_redacts_github_oauth_token():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="failure: gho_abcdefghijklmnopqrstuvwxyz0123456789",
        args=(), exc_info=None,
    )
    SecretRedactor().filter(record)
    assert "gho_abcdefghijklmnopqrstuvwxyz0123456789" not in record.getMessage()


def test_logging_filter_negative_non_token_string():
    """Benign strings that vaguely resemble a token prefix stay intact."""
    # These should NOT be redacted:
    benign_cases = [
        "not a ghp_",
        "ghp_short",  # too short for the 30+ char tail
        "glpat-short",  # too short for 20+ char tail
        "regular log message without tokens",
    ]
    for msg in benign_cases:
        assert redact_secrets(msg) == msg, (
            f"Expected no redaction on {msg!r}, got {redact_secrets(msg)!r}"
        )


# ──────────────────────────────────────────────────────────────────
# redact_token helper (used in clone_repo exception paths)
# ──────────────────────────────────────────────────────────────────


def test_redact_token_replaces_occurrences():
    text = f"auth failed for https://oauth2:{_GITLAB_TOKEN}@gitlab.com/x.git"
    result = redact_token(text, _GITLAB_TOKEN)
    assert _GITLAB_TOKEN not in result
    assert "***REDACTED***" in result


def test_redact_token_empty_token_is_noop():
    text = "some message without token"
    assert redact_token(text, "") == text
