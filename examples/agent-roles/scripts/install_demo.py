#!/usr/bin/env python3
"""Filmable local install and MCP relay verification demo."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import getpass
import time
import warnings
from typing import Any, Iterator

from credentials_story import run_credentials_story
from provider_inference_demo import (
    CLAUDE_INFERENCE_CMD_DISPLAY,
    INFERENCE_ROLE,
    MAX_PASSPHRASE_BYTES,
    MIN_PASSPHRASE_BYTES,
    build_unlock_envelope,
)

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ("anthropic", "mistral", "gemini", "openai")
VAULT_ROLE = "refund-demo"
INFERENCE_VAULT_ROLE = INFERENCE_ROLE
ADD_ANTHROPIC_OUTPUT_RE = re.compile(
    r"^stored anthropic \(anthropic/refund_operator\) ([0-9a-f]{12})$"
)
INFERENCE_LINE_RE = re.compile(
    r"^INFERENCE: provider=anthropic fingerprint=([0-9a-f]{12}) status=ok$"
)

UUID_PART = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
DENIAL_REASON = "argument_constraint_denied"
AMOUNT_CONSTRAINT = "amount_exceeds_cap"
CLAUDE_ADD_LINE = (
    '$ claude mcp add --scope local refunds -- "$STOACTL" relay connect --socket "$RELAY_SOCKET"'
)
REFUSAL_LINE_RE = re.compile(
    rf"CALL 2 \(EUR 80\): refused \| decision_id={UUID_PART} \| "
    rf"reason={DENIAL_REASON} \| constraint={AMOUNT_CONSTRAINT} \| limit_eur=50 \| "
    r"Tool call rejected by role policy"
)
ALLOW_CALL_LINE_RE = re.compile(
    rf"CALL 1 \(EUR 50\): allowed \| decision_id={UUID_PART} \| simulated"
)
ALLOW_JOURNAL_LINE_RE = re.compile(
    rf"JOURNAL: decision=allowed decision_id={UUID_PART} \| "
    rf"execution=succeeded decision_id={UUID_PART}"
)
DENY_JOURNAL_LINE_RE = re.compile(
    rf"JOURNAL: decision=denied reason={DENIAL_REASON} decision_id={UUID_PART}"
)
CONNECT_LINE_RE = re.compile(r"CONNECT (claude|vibe|antigravity|codex): attached")
EXPECTED_STORY_CLIENTS = frozenset({"claude", "vibe", "antigravity", "codex"})
ALLOWED_CHILD_PATTERNS = (
    re.compile(
        r"INIT: gateway=ready parent_cap=500 EUR \(Ed25519 signed\) "
        r"child_cap=50 EUR customer=C-1042"
    ),
    re.compile(re.escape(CLAUDE_ADD_LINE)),
    re.compile(
        r"MCP_PROBE: direct MCP stdio probe reading real Claude CLI local config "
        r"\(no model inference; no vault keys forwarded\)"
    ),
    re.compile(r"=== stoactl plugs the agents into the gateway\. ==="),
    CONNECT_LINE_RE,
    re.compile(r"=== Same agents, now governed\. ==="),
    ALLOW_CALL_LINE_RE,
    ALLOW_JOURNAL_LINE_RE,
    REFUSAL_LINE_RE,
    DENY_JOURNAL_LINE_RE,
    re.compile(r"EXPORT: locked journal verified \(3 rows\)"),
    re.compile(r"UPSTREAM: caller_auth_headers_seen=0"),
    re.compile(re.escape(CLAUDE_INFERENCE_CMD_DISPLAY)),
    INFERENCE_LINE_RE,
)


class InstallDemoError(Exception):
    """Sanitized user-facing error."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise InstallDemoError(
            "Invalid command-line arguments. Use --show [--verify-local [--story] | --story [--split] [--anthropic-key-file PATH] | --load-provider-keys]."
        )


def _handle_sigterm(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt()


def _handle_sigalrm(_signum: int, _frame: Any) -> None:
    raise TimeoutError()


@contextmanager
def _private_workspace() -> Iterator[Path]:
    try:
        root = Path(tempfile.mkdtemp(prefix="stoa-install-", dir="/tmp")).resolve()
        os.chmod(root, 0o700)
    except OSError as exc:
        raise InstallDemoError("Failed to create temporary workspace.") from exc
    try:
        yield root
    finally:
        if root.exists():
            try:
                shutil.rmtree(root, ignore_errors=False)
            except OSError as exc:
                raise InstallDemoError("Failed to clean up temporary workspace.") from exc


def _resolve_stoactl_src(*, allow_split_fallback: bool = False) -> Path:
    raw = os.environ.get("STOA_POC_STOACTL_SRC", "")
    if not raw:
        if allow_split_fallback:
            repo = ROOT.parent.parent
            for candidate in (
                repo.parent / "stoa-v2" / "cli",
                Path.home() / "hlfh-repos" / "stoa-v2-wt" / repo.name / "cli",
            ):
                resolved = candidate.resolve()
                if resolved.is_dir() and (resolved / "go.mod").is_file():
                    return resolved
        raise InstallDemoError("STOA_POC_STOACTL_SRC must be set to an existing CLI module directory.")
    src = Path(raw).resolve()
    if not src.is_dir() or not (src / "go.mod").is_file():
        raise InstallDemoError("STOA_POC_STOACTL_SRC does not point to a valid Go CLI module.")
    return src


def _minimal_env(home_dir: Path, *, keep_term: bool = False) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home_dir),
        "LC_ALL": "C",
    }
    if keep_term:
        env["TERM"] = os.environ.get("TERM", "xterm-256color")
    return env


def _build_stoactl(src_dir: Path, bin_dir: Path, gocache_dir: Path, home_dir: Path) -> Path:
    if not shutil.which("go"):
        raise InstallDemoError("go executable not found in PATH.")
    stoactl_bin = bin_dir / "stoactl"
    env = _minimal_env(home_dir)
    env.update(
        {
            "GOCACHE": str(gocache_dir),
            "GOENV": "off",
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "GOWORK": "off",
            "GOTOOLCHAIN": "local",
        }
    )
    try:
        res = subprocess.run(
            [
                "go",
                "-C",
                str(src_dir),
                "build",
                "-mod=vendor",
                "-trimpath",
                "-o",
                str(stoactl_bin),
                ".",
            ],
            cwd=bin_dir.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallDemoError("Offline Go build of stoactl failed.") from exc
    if res.returncode != 0 or not stoactl_bin.is_file() or not os.access(stoactl_bin, os.X_OK):
        raise InstallDemoError("Offline Go build of stoactl failed.")
    return stoactl_bin


def _assert_vault_mode(vault_path: Path) -> None:
    if not vault_path.is_file():
        raise InstallDemoError("Vault file was not created.")
    mode = stat.S_IMODE(vault_path.stat().st_mode)
    if mode != 0o600:
        raise InstallDemoError("Vault file permissions are not 0600.")


def _put_synthetic(
    stoactl_bin: Path,
    vault_dir: Path,
    home_dir: Path,
    provider: str,
    passphrase: bytes,
    secret_value: bytes,
) -> None:
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, passphrase + b"\n")
        os.close(w_fd)
        w_fd = -1
        res = subprocess.run(
            [
                str(stoactl_bin),
                "credentials",
                "put",
                "--vault",
                "./vault.enc",
                "--name",
                provider,
                "--provider",
                provider,
                "--role",
                VAULT_ROLE,
                "--passphrase-fd",
                str(r_fd),
            ],
            cwd=vault_dir,
            env=_minimal_env(home_dir),
            input=secret_value + b"\n",
            capture_output=True,
            pass_fds=(r_fd,),
            close_fds=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallDemoError(f"Failed to store synthetic credential for {provider}.") from exc
    finally:
        if w_fd != -1:
            os.close(w_fd)
        os.close(r_fd)

    if res.returncode != 0:
        raise InstallDemoError(f"stoactl credentials put failed for {provider}.")
    if passphrase in res.stdout or passphrase in res.stderr:
        raise InstallDemoError("Synthetic passphrase appeared in subprocess output.")
    if secret_value in res.stdout or secret_value in res.stderr:
        raise InstallDemoError("Synthetic credential value appeared in subprocess output.")


def _put_real(stoactl_bin: Path, vault_dir: Path, home_dir: Path, provider: str) -> None:
    if not sys.stdin.isatty():
        raise InstallDemoError("Interactive TTY stdin is required for --load-provider-keys.")
    try:
        proc = subprocess.Popen(
            [
                str(stoactl_bin),
                "credentials",
                "put",
                "--vault",
                "./vault.enc",
                "--name",
                provider,
                "--provider",
                provider,
                "--role",
                VAULT_ROLE,
            ],
            cwd=vault_dir,
            env=_minimal_env(home_dir, keep_term=True),
            stdin=None,
            stdout=subprocess.DEVNULL,
            stderr=None,
            close_fds=True,
        )
    except OSError as exc:
        raise InstallDemoError("Failed to store credential.") from exc
    try:
        rc = proc.wait(timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise InstallDemoError("Timed out waiting for masked credential input.") from exc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    if rc != 0:
        raise InstallDemoError("stoactl credentials put failed.")


def _read_vault_passphrase() -> bytes:
    if not sys.stdin.isatty():
        raise InstallDemoError("Interactive TTY stdin is required for live inference mode.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            raw = getpass.getpass("Vault passphrase: ")
    except (getpass.GetPassWarning, EOFError, OSError) as exc:
        raise InstallDemoError("Unable to read masked vault passphrase from controlling TTY.") from exc
    passphrase = raw.encode("utf-8")
    if not (MIN_PASSPHRASE_BYTES <= len(passphrase) <= MAX_PASSPHRASE_BYTES):
        raise InstallDemoError(
            f"Vault passphrase must be between {MIN_PASSPHRASE_BYTES} and {MAX_PASSPHRASE_BYTES} UTF-8 bytes."
        )
    return passphrase


def _open_owner_key_fd(raw_path: str) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = -1
    try:
        fd = os.open(raw_path, flags)
        st = os.fstat(fd)
        if (
            not stat.S_ISREG(st.st_mode)
            or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) != 0o600
            or st.st_nlink != 1
            or not (1 <= st.st_size <= 4097)
        ):
            os.close(fd)
            fd = -1
            raise InstallDemoError(
                "Anthropic key file must be a regular owner-only (0600) file with 1..4097 bytes."
            )
        return fd
    except InstallDemoError:
        raise
    except OSError as exc:
        if fd != -1:
            os.close(fd)
        raise InstallDemoError(
            "Anthropic key file must be a regular owner-only (0600) file with 1..4097 bytes."
        ) from exc


def _add_real_anthropic(
    stoactl_bin: Path,
    vault_dir: Path,
    home_dir: Path,
    passphrase: bytes,
    *,
    key_fd: int | None = None,
) -> str:
    if key_fd is None and not sys.stdin.isatty():
        raise InstallDemoError("Interactive TTY stdin is required for live inference mode.")
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, passphrase + b"\n")
        os.close(w_fd)
        w_fd = -1
        proc = subprocess.Popen(
            [
                str(stoactl_bin),
                "credentials",
                "add",
                "anthropic",
                "--vault",
                "./vault.enc",
                "--role",
                INFERENCE_VAULT_ROLE,
                "--passphrase-fd",
                str(r_fd),
            ],
            cwd=vault_dir,
            env=_minimal_env(home_dir, keep_term=(key_fd is None)),
            stdin=key_fd if key_fd is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if key_fd is not None else None,
            pass_fds=(r_fd,),
            close_fds=True,
        )
    except OSError as exc:
        raise InstallDemoError("Failed to store Anthropic credential.") from exc
    finally:
        if w_fd != -1:
            os.close(w_fd)
        os.close(r_fd)

    try:
        stdout_bytes, _ = proc.communicate(timeout=180)
    except subprocess.TimeoutExpired as exc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise InstallDemoError("Timed out waiting for masked credential input.") from exc
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise

    if proc.returncode != 0:
        raise InstallDemoError("stoactl credentials add failed.")
    if passphrase in stdout_bytes:
        raise InstallDemoError("Vault passphrase appeared in subprocess output.")
    try:
        text = stdout_bytes.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise InstallDemoError("Unexpected output from stoactl credentials add.") from exc
    match = ADD_ANTHROPIC_OUTPUT_RE.fullmatch(text)
    if not match:
        raise InstallDemoError("Unexpected metadata output from stoactl credentials add.")
    return match.group(1)


def _verify_install_env(stoactl_bin: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "STOA_POC_STOACTL_BIN": str(stoactl_bin),
    }
    if "DOCKER_HOST" in os.environ:
        env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]
    return env


def _is_allowed_child_line(line: str) -> bool:
    return any(pat.fullmatch(line) for pat in ALLOWED_CHILD_PATTERNS)


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    parser = _SafeArgumentParser(description="STOA local install and MCP verification demo.")
    parser.add_argument("--show", action="store_true", help="Run the filmable local demo.")
    parser.add_argument(
        "--verify-local",
        action="store_true",
        help="Run synthetic 4-provider local verification without live model inference.",
    )
    parser.add_argument(
        "--story",
        action="store_true",
        help="Run the credential migration story (with --verify-local for chapters 1-3 or --anthropic-key-file for chapters 1-5).",
    )
    parser.add_argument(
        "--anthropic-key-file",
        help="Path to owner-only (0600) Anthropic API key file for full story chapters 4-5 (requires --story).",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Run full story chapters 4-5 in a split tmux terminal (requires --show --story and a TTY).",
    )
    parser.add_argument(
        "--load-provider-keys",
        action="store_true",
        help="Legacy local 4-provider masked terminal input without live model inference.",
    )
    args = parser.parse_args(argv)
    if not args.show:
        raise InstallDemoError("--show is required.")
    if args.split:
        if not args.story or args.verify_local or args.load_provider_keys:
            raise InstallDemoError(
                "--split requires --story and cannot be combined with --verify-local or --load-provider-keys."
            )
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise InstallDemoError("--split requires a real TTY.")
        if not shutil.which("tmux"):
            raise InstallDemoError("--split requires tmux in PATH.")
    if args.anthropic_key_file:
        if not args.story or args.verify_local or args.load_provider_keys:
            raise InstallDemoError(
                "--anthropic-key-file requires --story and cannot be combined with --verify-local or --load-provider-keys."
            )
    if args.story and args.load_provider_keys:
        raise InstallDemoError("--story cannot be combined with --load-provider-keys.")
    if args.story and not (args.verify_local or args.anthropic_key_file or args.split):
        raise InstallDemoError(
            "Use --story --verify-local for chapters 1-3 or --story --anthropic-key-file / --story --split for the full story."
        )
    if args.verify_local and args.load_provider_keys:
        raise InstallDemoError("--verify-local and --load-provider-keys cannot be combined.")
    story_full = bool(args.story and (args.anthropic_key_file or args.split))
    story_split = bool(args.split)
    live_inference = not args.verify_local and not args.load_provider_keys and not args.story

    src_dir = _resolve_stoactl_src(allow_split_fallback=story_split)
    t0 = time.monotonic()
    cmd_count = 0

    def emit_cmd(cmd_line: str) -> None:
        nonlocal cmd_count
        cmd_count += 1
        print(cmd_line, flush=True)

    if story_full:
        print(
            "MODE: full story (local synthetic migration + live governed Claude inference via isolated gateway)",
            flush=True,
        )
    elif args.story:
        print(
            "MODE: story local proof (synthetic keys in disposable $DEMO_HOME; real stoactl CLI + unauthenticated provider probes)",
            flush=True,
        )
    elif live_inference:
        print(
            "MODE: live Anthropic inference via isolated gateway (masked key in ephemeral vault; bills provider)",
            flush=True,
        )
    elif args.load_provider_keys:
        print(
            "MODE: masked terminal input via stoactl (vault role is metadata; no keys forwarded)",
            flush=True,
        )
    else:
        print(
            "MODE: synthetic (in-memory generated values, never displayed; no keys forwarded)",
            flush=True,
        )

    with _private_workspace() as root:
        bin_dir = root / "bin"
        gocache_dir = root / "gocache"
        vault_dir = root / "vault"
        home_dir = root / "home"
        for d in (bin_dir, gocache_dir, vault_dir, home_dir):
            os.mkdir(d, 0o700)

        emit_cmd('$ go -C "$STOA_POC_STOACTL_SRC" build -mod=vendor -trimpath -o "$DEMO_BIN/stoactl" .')
        stoactl_bin = _build_stoactl(src_dir, bin_dir, gocache_dir, home_dir)
        print("BUILD: ok (fresh binary and fresh GOCACHE)", flush=True)

        story_elapsed: float | None = None
        full_story_elapsed: float | None = None
        elapsed_to_refusal: float | None = None
        if args.story:
            story_elapsed = run_credentials_story(
                stoactl_bin=stoactl_bin,
                root=root,
                emit_cmd=emit_cmd,
                t0=t0,
                error_cls=InstallDemoError,
                assert_vault_mode=_assert_vault_mode,
                minimal_env=_minimal_env,
            )
            if cmd_count != 6:
                raise InstallDemoError("Unexpected command count in story mode.")
            if story_full:
                anthropic_key_file = args.anthropic_key_file or (
                    str(Path.home() / ".stoa-demo" / "anthropic.key") if story_split else None
                )
                assert anthropic_key_file is not None
                story_vault_dir = root / "story_vault"
                os.mkdir(story_vault_dir, 0o700)
                story_home = root / "demo_home"
                if not story_home.is_dir() or story_home.is_symlink():
                    raise InstallDemoError("Disposable story HOME was not prepared.")
                passphrase = secrets.token_urlsafe(32).encode("ascii")
                emit_cmd(
                    f'$ stoactl credentials add anthropic --vault "$STORY_VAULT/vault.enc" '
                    f'--role {INFERENCE_VAULT_ROLE} < "$ANTHROPIC_KEY_FILE"'
                )
                key_fd = _open_owner_key_fd(anthropic_key_file)
                try:
                    expected_fingerprint = _add_real_anthropic(
                        stoactl_bin,
                        story_vault_dir,
                        home_dir,
                        passphrase,
                        key_fd=key_fd,
                    )
                finally:
                    os.close(key_fd)
                print(f"VAULT: ok (anthropic, fingerprint={expected_fingerprint})", flush=True)
                story_vault_path = story_vault_dir / "vault.enc"
                _assert_vault_mode(story_vault_path)
                vault_bytes = story_vault_path.read_bytes()
                if passphrase in vault_bytes:
                    raise InstallDemoError("Vault file contains cleartext passphrase.")
                unlock_envelope = build_unlock_envelope(passphrase, vault_bytes)

                split_sock = story_home.parent / "split.sock"
                if story_split:
                    child_cmd = [
                        str(ROOT / "scripts" / "agent_demo.sh"),
                        "--verify-story",
                        "--story-split",
                        "--story-home",
                        str(story_home),
                        "--expected-fingerprint",
                        expected_fingerprint,
                    ]
                    emit_cmd(
                        '$ STOA_POC_STOACTL_BIN="$DEMO_BIN/stoactl" ./scripts/agent_demo.sh '
                        '--verify-story --story-split --story-home "$DEMO_HOME"'
                    )
                else:
                    child_cmd = [
                        str(ROOT / "scripts" / "agent_demo.sh"),
                        "--verify-story",
                        "--headless",
                        "--story-home",
                        str(story_home),
                    ]
                    emit_cmd(
                        '$ STOA_POC_STOACTL_BIN="$DEMO_BIN/stoactl" ./scripts/agent_demo.sh '
                        '--verify-story --headless --story-home "$DEMO_HOME"'
                    )
                observed_fingerprint: str | None = None
                connect_seen: set[str] = set()
                allow_call_seen = False
                allow_journal_seen = False
                deny_call_seen = False
                deny_journal_seen = False
                split_ready_seen = False
                attach_proc: subprocess.Popen[bytes] | None = None
                passphrase_str = passphrase.decode("ascii")
                try:
                    proc = subprocess.Popen(
                        child_cmd,
                        cwd=ROOT,
                        env=_verify_install_env(stoactl_bin),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        close_fds=True,
                        start_new_session=True,
                    )
                except OSError as exc:
                    raise InstallDemoError("Failed to start story verification.") from exc
                prev_alrm = signal.signal(signal.SIGALRM, _handle_sigalrm)
                signal.alarm(240)
                try:
                    assert proc.stdin is not None
                    try:
                        proc.stdin.write(unlock_envelope)
                        proc.stdin.flush()
                    except BrokenPipeError as exc:
                        raise InstallDemoError("Verification child closed unlock pipe early.") from exc
                    finally:
                        proc.stdin.close()
                    assert proc.stdout is not None
                    while True:
                        raw_line = proc.stdout.readline(513)
                        if not raw_line:
                            break
                        if len(raw_line) > 512 or not raw_line.endswith(b"\n"):
                            raise InstallDemoError("Verification output malformed.")
                        try:
                            line = raw_line.decode("utf-8", errors="strict").rstrip("\r\n")
                        except UnicodeDecodeError as exc:
                            raise InstallDemoError("Verification output malformed.") from exc
                        if passphrase_str in line or line.startswith("$ "):
                            raise InstallDemoError("Verification output malformed.")
                        if story_split and line == "SPLIT_READY":
                            if split_ready_seen:
                                raise InstallDemoError("Duplicate split ready marker from verification child.")
                            split_ready_seen = True
                            attach_env = {
                                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                "TERM": os.environ.get("TERM", "xterm-256color"),
                            }
                            try:
                                attach_proc = subprocess.Popen(
                                    [
                                        "tmux",
                                        "-u",
                                        "-S",
                                        str(split_sock),
                                        "-f",
                                        "/dev/null",
                                        "attach-session",
                                        "-t",
                                        "stoa",
                                    ],
                                    env=attach_env,
                                    close_fds=True,
                                )
                            except OSError as exc:
                                raise InstallDemoError("Failed to attach split tmux session.") from exc
                            continue
                        if not _is_allowed_child_line(line):
                            raise InstallDemoError("Verification output malformed.")
                        conn_match = CONNECT_LINE_RE.fullmatch(line)
                        if conn_match:
                            connect_seen.add(conn_match.group(1))
                        elif ALLOW_CALL_LINE_RE.fullmatch(line):
                            allow_call_seen = True
                        elif ALLOW_JOURNAL_LINE_RE.fullmatch(line):
                            allow_journal_seen = True
                        elif REFUSAL_LINE_RE.fullmatch(line):
                            deny_call_seen = True
                        elif DENY_JOURNAL_LINE_RE.fullmatch(line):
                            deny_journal_seen = True
                        inf_match = INFERENCE_LINE_RE.fullmatch(line)
                        if inf_match:
                            if observed_fingerprint is not None:
                                raise InstallDemoError("Duplicate inference output from verification child.")
                            if inf_match.group(1) != expected_fingerprint:
                                raise InstallDemoError("Gateway inference fingerprint did not match vault credential.")
                            observed_fingerprint = inf_match.group(1)
                        if not story_split:
                            print(line, flush=True)
                    rc = proc.wait()
                except TimeoutError as exc:
                    raise InstallDemoError("Story verification timed out.") from exc
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, prev_alrm)
                    if attach_proc is not None:
                        if attach_proc.poll() is None:
                            try:
                                attach_proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                try:
                                    attach_proc.terminate()
                                    attach_proc.wait(timeout=2)
                                except (OSError, subprocess.TimeoutExpired):
                                    try:
                                        attach_proc.kill()
                                        attach_proc.wait(timeout=2)
                                    except (OSError, subprocess.TimeoutExpired):
                                        pass
                    if proc.stdout is not None:
                        proc.stdout.close()
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(proc.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            proc.wait(timeout=5)
                if rc != 0:
                    raise InstallDemoError("Story verification failed.")
                if story_split and not split_ready_seen:
                    raise InstallDemoError("Split verification did not reach ready state.")
                if connect_seen != EXPECTED_STORY_CLIENTS:
                    raise InstallDemoError("Not all four agents reported attached.")
                if not (allow_call_seen and allow_journal_seen and deny_call_seen and deny_journal_seen):
                    raise InstallDemoError("Expected paired governed refund results were not observed.")
                if observed_fingerprint != expected_fingerprint:
                    raise InstallDemoError("Expected inference verification output was not observed.")
                if cmd_count != 8:
                    raise InstallDemoError("Unexpected command count in full story mode.")
                full_story_elapsed = time.monotonic() - t0
        else:
            synthetic_secrets: list[bytes] = []
            expected_fingerprint: str | None = None
            unlock_envelope: bytes | None = None
            passphrase = b""

            if live_inference:
                passphrase = _read_vault_passphrase()
                emit_cmd(
                    f"$ stoactl credentials add anthropic --vault ./vault.enc --role {INFERENCE_VAULT_ROLE}"
                )
                expected_fingerprint = _add_real_anthropic(stoactl_bin, vault_dir, home_dir, passphrase)
                print(f"VAULT: ok (anthropic, fingerprint={expected_fingerprint})", flush=True)
            else:
                if not args.load_provider_keys:
                    passphrase = secrets.token_urlsafe(32).encode("ascii")
                    synthetic_secrets.append(passphrase)
                for provider in PROVIDERS:
                    emit_cmd(
                        f"$ stoactl credentials put --vault ./vault.enc --name {provider} "
                        f"--provider {provider} --role {VAULT_ROLE}"
                    )
                    if args.load_provider_keys:
                        _put_real(stoactl_bin, vault_dir, home_dir, provider)
                        print(f"VAULT: ok ({provider})", flush=True)
                    else:
                        val = secrets.token_urlsafe(32).encode("ascii")
                        synthetic_secrets.append(val)
                        _put_synthetic(stoactl_bin, vault_dir, home_dir, provider, passphrase, val)
                        print(f"VAULT: ok ({provider}, synthetic)", flush=True)

            vault_path = vault_dir / "vault.enc"
            _assert_vault_mode(vault_path)
            vault_bytes = vault_path.read_bytes()
            if synthetic_secrets:
                for secret in synthetic_secrets:
                    if secret in vault_bytes:
                        raise InstallDemoError("Vault file contains cleartext synthetic data.")
            if live_inference:
                if passphrase in vault_bytes:
                    raise InstallDemoError("Vault file contains cleartext passphrase.")
                unlock_envelope = build_unlock_envelope(passphrase, vault_bytes)

            child_cmd = [str(ROOT / "scripts" / "agent_demo.sh"), "--verify-install", "--headless"]
            if live_inference:
                child_cmd.append("--verify-inference")
                emit_cmd(
                    '$ STOA_POC_STOACTL_BIN="$DEMO_BIN/stoactl" ./scripts/agent_demo.sh '
                    "--verify-install --headless --verify-inference"
                )
            else:
                emit_cmd(
                    '$ STOA_POC_STOACTL_BIN="$DEMO_BIN/stoactl" ./scripts/agent_demo.sh '
                    "--verify-install --headless"
                )

            observed_fingerprint: str | None = None
            secret_strs = [s.decode("ascii") for s in synthetic_secrets]
            if live_inference:
                secret_strs.append(passphrase.decode("utf-8"))
            try:
                proc = subprocess.Popen(
                    child_cmd,
                    cwd=ROOT,
                    env=_verify_install_env(stoactl_bin),
                    stdin=subprocess.PIPE if live_inference else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
            except OSError as exc:
                raise InstallDemoError("Failed to start install verification.") from exc
            prev_alrm = signal.signal(signal.SIGALRM, _handle_sigalrm)
            signal.alarm(180 if live_inference else 120)
            try:
                if live_inference:
                    assert proc.stdin is not None and unlock_envelope is not None
                    try:
                        proc.stdin.write(unlock_envelope)
                        proc.stdin.flush()
                    except BrokenPipeError as exc:
                        raise InstallDemoError("Verification child closed unlock pipe early.") from exc
                    finally:
                        proc.stdin.close()
                assert proc.stdout is not None
                while True:
                    raw_line = proc.stdout.readline(513)
                    if not raw_line:
                        break
                    if len(raw_line) > 512 or not raw_line.endswith(b"\n"):
                        raise InstallDemoError("Verification output malformed.")
                    try:
                        line = raw_line.decode("utf-8", errors="strict").rstrip("\r\n")
                    except UnicodeDecodeError as exc:
                        raise InstallDemoError("Verification output malformed.") from exc
                    if any(secret and secret in line for secret in secret_strs):
                        raise InstallDemoError("Verification output malformed.")
                    if not _is_allowed_child_line(line):
                        raise InstallDemoError("Verification output malformed.")
                    inf_match = INFERENCE_LINE_RE.fullmatch(line)
                    if inf_match:
                        if not live_inference:
                            raise InstallDemoError("Unexpected inference output in local mode.")
                        if observed_fingerprint is not None:
                            raise InstallDemoError("Duplicate inference output from verification child.")
                        if inf_match.group(1) != expected_fingerprint:
                            raise InstallDemoError("Gateway inference fingerprint did not match vault credential.")
                        observed_fingerprint = inf_match.group(1)
                    elif line == CLAUDE_INFERENCE_CMD_DISPLAY and not live_inference:
                        raise InstallDemoError("Unexpected inference command in local mode.")
                    if line.startswith("$ "):
                        cmd_count += 1
                    print(line, flush=True)
                    if elapsed_to_refusal is None and REFUSAL_LINE_RE.fullmatch(line):
                        elapsed_to_refusal = time.monotonic() - t0
                rc = proc.wait()
            except TimeoutError as exc:
                raise InstallDemoError("Install verification timed out.") from exc
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, prev_alrm)
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        proc.wait(timeout=5)

            if rc != 0:
                raise InstallDemoError("Install verification failed.")
            if elapsed_to_refusal is None:
                raise InstallDemoError("Expected refusal was not observed during verification.")
            if live_inference and observed_fingerprint is None:
                raise InstallDemoError("Expected inference verification output was not observed.")
            if cmd_count > 8:
                raise InstallDemoError("Command count exceeded limit.")

    if full_story_elapsed is not None:
        print(
            f"SUMMARY: commands={cmd_count} elapsed={full_story_elapsed:.2f}s",
            flush=True,
        )
        return 0

    if story_elapsed is not None:
        print(
            f"SUMMARY: commands={cmd_count} elapsed_to_direct_auth_proof={story_elapsed:.2f}s",
            flush=True,
        )
        print("Local proof: credential migration and direct auth refusal.", flush=True)
        return 0

    print(
        f"SUMMARY: commands={cmd_count} elapsed_to_first_refusal={elapsed_to_refusal:.2f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("ERROR: Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except InstallDemoError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("ERROR: Unexpected install demo failure.", file=sys.stderr)
        raise SystemExit(1)
