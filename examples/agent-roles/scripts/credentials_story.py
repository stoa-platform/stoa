#!/usr/bin/env python3
"""Optional local story mode (chapters 1-3) for STOA A2 credential migration proof."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from typing import Callable

STORY_ROLE = "refund_operator"
STORY_PROVIDERS = ("anthropic", "mistral", "gemini", "openai")

CARD_1 = "Today: your API keys sit in plain-text config files."
CARD_2 = "stoactl moves them into an encrypted vault."
CARD_3 = "The agents no longer hold any key."

INSPECT_HEADER_RE = re.compile(r"^PROVIDER\s+PATH\s+STATUS$")
INSPECT_ROW_RES = {
    "anthropic": re.compile(r"^anthropic\s+(?:~/|\$HOME/)?\.claude/settings\.json\s+\[MASKED\]$"),
    "mistral": re.compile(r"^mistral\s+(?:~/|\$HOME/)?\.vibe/\.env\s+\[MASKED\]$"),
    "gemini": re.compile(r"^gemini\s+(?:~/|\$HOME/)?\.gemini/\.env\s+\[MASKED\]$"),
    "openai": re.compile(r"^openai\s+(?:~/|\$HOME/)?\.codex/auth\.json\s+\[MASKED\]$"),
}

IMPORT_HEADER_RE = re.compile(r"^NAME\s+PROVIDER\s+ROLE\s+FINGERPRINT\s+STATUS$")
IMPORT_ROW_RE = re.compile(
    r"^(anthropic|mistral|gemini|openai)\s+\1\s+refund_operator\s+([0-9a-f]{12})\s+imported$"
)

LIST_HEADER_RE = re.compile(r"^NAME\s+PROVIDER\s+ROLE\s+CREATED\s+FINGERPRINT$")
LIST_ROW_RE = re.compile(
    r"^(anthropic|mistral|gemini|openai)\s+\1\s+refund_operator\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\s+([0-9a-f]{12})$"
)

VERIFY_HEADER_RE = re.compile(r"^PROVIDER\s+STATUS$")
VERIFY_ROW_RE = re.compile(r"^(anthropic|mistral|gemini|openai)\s+missing$")

PROBE_ROW_RES = {
    "anthropic": re.compile(r"^anthropic:\s+(?:401|403)$"),
    "mistral": re.compile(r"^mistral:\s+(?:401|403)$"),
    "gemini": re.compile(r"^(?:gemini|google):\s+(?:400|401|403)$"),
    "openai": re.compile(r"^openai:\s+(?:401|403)$"),
}


def _write_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _seed_synthetic_home(demo_home: Path) -> dict[str, bytes]:
    _write_private_file(
        demo_home / ".stoa-disposable-home",
        "stoa-disposable-home-v1\n",
    )
    keys = {
        provider: f"synth-local-{provider}-{secrets.token_urlsafe(24)}".encode("ascii")
        for provider in STORY_PROVIDERS
    }
    _write_private_file(
        demo_home / ".claude" / "settings.json",
        json.dumps({"env": {"ANTHROPIC_API_KEY": keys["anthropic"].decode("ascii")}}, indent=2) + "\n",
    )
    _write_private_file(
        demo_home / ".vibe" / ".env",
        f"MISTRAL_API_KEY={keys['mistral'].decode('ascii')}\n",
    )
    _write_private_file(
        demo_home / ".gemini" / ".env",
        f"GEMINI_API_KEY={keys['gemini'].decode('ascii')}\n",
    )
    _write_private_file(
        demo_home / ".codex" / "auth.json",
        json.dumps({"OPENAI_API_KEY": keys["openai"].decode("ascii")}, indent=2) + "\n",
    )
    return keys


def _run_stoactl(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    canaries: list[bytes],
    error_cls: type[Exception],
    label: str,
    passphrase: bytes | None = None,
    timeout: int = 30,
) -> list[str]:
    r_fd = -1
    w_fd = -1
    cmd = list(args)
    pass_fds: tuple[int, ...] = ()
    try:
        if passphrase is not None:
            r_fd, w_fd = os.pipe()
            os.write(w_fd, passphrase + b"\n")
            os.close(w_fd)
            w_fd = -1
            cmd.extend(["--passphrase-fd", str(r_fd)])
            pass_fds = (r_fd,)
        res = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            pass_fds=pass_fds,
            close_fds=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise error_cls(f"{label} failed.") from exc
    finally:
        if w_fd != -1:
            os.close(w_fd)
        if r_fd != -1:
            os.close(r_fd)

    for secret in canaries:
        if secret in res.stdout or secret in res.stderr:
            raise error_cls(f"Synthetic secret appeared in {label} output.")
    if res.returncode != 0:
        raise error_cls(f"{label} exited with non-zero status.")
    try:
        text = res.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise error_cls(f"{label} produced non-UTF-8 output.") from exc
    return [line.rstrip("\r") for line in text.splitlines() if line.strip()]


def _scan_tree_for_canaries(roots: tuple[Path, ...], canaries: list[bytes], error_cls: type[Exception]) -> None:
    for base in roots:
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                fpath = Path(dirpath) / name
                if not fpath.is_file():
                    continue
                try:
                    data = fpath.read_bytes()
                except OSError as exc:
                    raise error_cls("Failed to scan workspace files for scrubbed keys.") from exc
                for secret in canaries:
                    if secret in data:
                        raise error_cls("Synthetic secret remained on disk after migration.")


def _emit_card(text: str) -> None:
    print(f"\n=== {text} ===", flush=True)


def run_credentials_story(
    *,
    stoactl_bin: Path,
    root: Path,
    emit_cmd: Callable[[str], None],
    t0: float,
    error_cls: type[Exception],
    assert_vault_mode: Callable[[Path], None],
    minimal_env: Callable[[Path], dict[str, str]],
) -> float:
    demo_home = root / "demo_home"
    vault_dir = root / "vault"
    vault_path = vault_dir / "vault.enc"
    os.mkdir(demo_home, 0o700)

    passphrase = secrets.token_urlsafe(32).encode("ascii")
    synth_keys = _seed_synthetic_home(demo_home)
    canaries = [passphrase, *synth_keys.values()]
    env = minimal_env(demo_home)

    print(
        "FIXTURE: synthetic in-memory keys seeded in disposable $DEMO_HOME "
        "(real profiles untouched; .gemini/.env models Gemini CLI settings, "
        "native Antigravity reads credentials from environment, not .env; "
        "role refund_operator is metadata only)",
        flush=True,
    )

    # Chapter 1
    _emit_card(CARD_1)
    emit_cmd('$ stoactl credentials import --inspect --from-home "$DEMO_HOME"')
    inspect_lines = _run_stoactl(
        [str(stoactl_bin), "credentials", "import", "--inspect", "--from-home", str(demo_home)],
        cwd=root,
        env=env,
        canaries=canaries,
        error_cls=error_cls,
        label="stoactl credentials import --inspect",
    )
    if len(inspect_lines) != 5 or not INSPECT_HEADER_RE.fullmatch(inspect_lines[0]):
        raise error_cls("Unexpected output from stoactl credentials import --inspect.")
    seen_inspect: set[str] = set()
    for line in inspect_lines[1:]:
        matched = False
        for provider, pat in INSPECT_ROW_RES.items():
            if pat.fullmatch(line):
                seen_inspect.add(provider)
                matched = True
                break
        if not matched:
            raise error_cls("Unexpected row in stoactl credentials import --inspect output.")
    if seen_inspect != set(STORY_PROVIDERS):
        raise error_cls("Incomplete provider set from stoactl credentials import --inspect.")
    for line in inspect_lines:
        print(line, flush=True)

    # Chapter 2
    _emit_card(CARD_2)
    emit_cmd(
        '$ stoactl credentials import --from-home "$DEMO_HOME" --vault "$DEMO_VAULT" --role refund_operator'
    )
    import_lines = _run_stoactl(
        [
            str(stoactl_bin),
            "credentials",
            "import",
            "--from-home",
            str(demo_home),
            "--vault",
            str(vault_path),
            "--role",
            STORY_ROLE,
        ],
        cwd=root,
        env=env,
        canaries=canaries,
        error_cls=error_cls,
        label="stoactl credentials import",
        passphrase=passphrase,
    )
    if len(import_lines) != 5 or not IMPORT_HEADER_RE.fullmatch(import_lines[0]):
        raise error_cls("Unexpected output from stoactl credentials import.")
    imported_fps: dict[str, str] = {}
    for line in import_lines[1:]:
        m = IMPORT_ROW_RE.fullmatch(line)
        if not m:
            raise error_cls("Unexpected row in stoactl credentials import output.")
        imported_fps[m.group(1)] = m.group(2)
    if set(imported_fps) != set(STORY_PROVIDERS):
        raise error_cls("Incomplete provider set from stoactl credentials import.")
    for line in import_lines:
        print(line, flush=True)

    assert_vault_mode(vault_path)
    _scan_tree_for_canaries((demo_home, vault_dir), canaries, error_cls)

    emit_cmd('$ stoactl credentials list --vault "$DEMO_VAULT"')
    list_lines = _run_stoactl(
        [str(stoactl_bin), "credentials", "list", "--vault", str(vault_path)],
        cwd=root,
        env=env,
        canaries=canaries,
        error_cls=error_cls,
        label="stoactl credentials list",
        passphrase=passphrase,
    )
    if len(list_lines) != 5 or not LIST_HEADER_RE.fullmatch(list_lines[0]):
        raise error_cls("Unexpected output from stoactl credentials list.")
    listed_fps: dict[str, str] = {}
    for line in list_lines[1:]:
        m = LIST_ROW_RE.fullmatch(line)
        if not m:
            raise error_cls("Unexpected row in stoactl credentials list output.")
        listed_fps[m.group(1)] = m.group(2)
    if listed_fps != imported_fps:
        raise error_cls("Vault metadata list did not match imported credentials.")
    for line in list_lines:
        print(line, flush=True)

    # Chapter 3
    _emit_card(CARD_3)
    emit_cmd('$ stoactl credentials import --verify --from-home "$DEMO_HOME"')
    verify_lines = _run_stoactl(
        [str(stoactl_bin), "credentials", "import", "--verify", "--from-home", str(demo_home)],
        cwd=root,
        env=env,
        canaries=canaries,
        error_cls=error_cls,
        label="stoactl credentials import --verify",
    )
    if len(verify_lines) != 5 or not VERIFY_HEADER_RE.fullmatch(verify_lines[0]):
        raise error_cls("Unexpected output from stoactl credentials import --verify.")
    seen_verify: set[str] = set()
    for line in verify_lines[1:]:
        m = VERIFY_ROW_RE.fullmatch(line)
        if not m:
            raise error_cls("Unexpected row in stoactl credentials import --verify output.")
        seen_verify.add(m.group(1))
    if seen_verify != set(STORY_PROVIDERS):
        raise error_cls("Incomplete provider set from stoactl credentials import --verify.")
    for line in verify_lines:
        print(line, flush=True)

    emit_cmd("$ stoactl credentials probe")
    probe_lines = _run_stoactl(
        [str(stoactl_bin), "credentials", "probe"],
        cwd=root,
        env=env,
        canaries=canaries,
        error_cls=error_cls,
        label="stoactl credentials probe",
        timeout=60,
    )
    if len(probe_lines) != 4:
        raise error_cls("Unexpected output from stoactl credentials probe.")
    seen_probe: set[str] = set()
    for line in probe_lines:
        matched = False
        for provider, pat in PROBE_ROW_RES.items():
            if pat.fullmatch(line):
                seen_probe.add(provider)
                matched = True
                break
        if not matched:
            raise error_cls("Unexpected row in stoactl credentials probe output.")
    if seen_probe != set(STORY_PROVIDERS):
        raise error_cls("Incomplete provider refusal set from stoactl credentials probe.")
    for line in probe_lines:
        print(line, flush=True)

    _scan_tree_for_canaries((demo_home, vault_dir), canaries, error_cls)
    return time.monotonic() - t0
