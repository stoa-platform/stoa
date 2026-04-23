"""Git credential helper for provider PATs (CP-1 C.2).

The previous ``clone_repo`` implementation injected the PAT into the
``git clone`` argv (``https://oauth2:<TOKEN>@host/repo``). Argv is
readable via ``ps`` / ``/proc/PID/cmdline`` by any local user and is
captured by container log scrapers — a DORA-grade disclosure.

This module routes credentials through GIT_ASKPASS instead:

- A per-call helper script is created in a private tempdir.
- The script dispatches on the prompt git emits (``Username for ...``
  vs ``Password for ...``) and prints the right value read from env vars.
- The token stays in the subprocess environment only, never in argv.

Reading env vars is restricted to the process owner on Linux
(``/proc/PID/environ`` uid-protected), a distinct threat boundary from
``/proc/PID/cmdline`` which is world-readable.

Supporting env forced on the child:
- GIT_ASKPASS=<helper>
- GIT_TERMINAL_PROMPT=0  — block interactive fallback if ASKPASS fails.
- GIT_TRACE=0, GIT_CURL_VERBOSE=0, GIT_TRACE_CURL=0,
  GIT_TRACE_PACKET=0, GIT_TRACE_SETUP=0 — prevent stderr dumps that
  would echo the bearer URL on failure paths.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

_HELPER_SCRIPT = """#!/bin/sh
# STOA git credential helper — GIT_ASKPASS target.
# $1 is the prompt git sends, e.g. "Username for 'https://...'" or "Password for ...".
case "$1" in
  Username*) printf '%s' "$STOA_GIT_USERNAME" ;;
  Password*) printf '%s' "$STOA_GIT_PASSWORD" ;;
  *)         printf '%s' "$STOA_GIT_PASSWORD" ;;
esac
"""

# Variables forced on the child process to prevent token leakage through
# git trace output. Keys only — values are always "0".
_TRACE_KILL_VARS = (
    "GIT_TRACE",
    "GIT_CURL_VERBOSE",
    "GIT_TRACE_CURL",
    "GIT_TRACE_PACKET",
    "GIT_TRACE_SETUP",
)


@contextlib.contextmanager
def askpass_env(username: str, password: str) -> Iterator[dict[str, str]]:
    """Yield an ``env`` dict for subprocess git invocations.

    The helper script is created in a private tempdir, chmod 0500, and
    deleted on context exit (success or failure). The yielded dict is
    designed to be passed as ``env=`` to ``asyncio.create_subprocess_exec``
    or ``subprocess.run``.

    Args:
        username: Git username (provider-specific — e.g. ``"oauth2"`` for
            GitLab, ``"x-access-token"`` for GitHub).
        password: The PAT / OAuth token. Passed to the child via
            ``STOA_GIT_PASSWORD`` env entry, never argv.

    Yields:
        A dict suitable for subprocess ``env=`` that contains PATH, HOME,
        the ASKPASS helper pointer, the credentials, and the trace-killing
        overrides.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="stoa-askpass-"))
    helper_path = tmpdir / "askpass.sh"
    try:
        helper_path.write_text(_HELPER_SCRIPT, encoding="utf-8")
        # Owner-only read+execute; no group/other bits, no write.
        os.chmod(helper_path, stat.S_IRUSR | stat.S_IXUSR)

        env: dict[str, str] = {
            # Preserve PATH and HOME so git can find itself and config.
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", str(tmpdir)),
            "GIT_ASKPASS": str(helper_path),
            "GIT_TERMINAL_PROMPT": "0",
            "STOA_GIT_USERNAME": username,
            "STOA_GIT_PASSWORD": password,
        }
        for key in _TRACE_KILL_VARS:
            env[key] = "0"

        yield env
    finally:
        # Always clean up the helper, even if the subprocess raised.
        try:
            if helper_path.exists():
                helper_path.unlink()
        except OSError as exc:  # best-effort; log and continue
            logger.warning("askpass helper cleanup failed for %s: %s", helper_path, exc)
        with contextlib.suppress(OSError):
            tmpdir.rmdir()


def redact_token(message: str, token: str) -> str:
    """Replace every occurrence of ``token`` in ``message`` with a placeholder.

    Used on subprocess stderr before surfacing it in exceptions so a
    misconfigured trace env (set outside our control) cannot leak the
    PAT into ``RuntimeError`` messages that land in logs.
    """
    if not token:
        return message
    return message.replace(token, "***REDACTED***")
