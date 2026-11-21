#!/usr/bin/env python3
"""Isolated provider vault unlock and live Anthropic inference verification for STOA PoC A2."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import struct
import subprocess
import time
from pathlib import Path
from typing import BinaryIO

MIN_PASSPHRASE_BYTES = 12
MAX_PASSPHRASE_BYTES = 1024
MIN_VAULT_BYTES = 72
MAX_VAULT_BYTES = 4 * 1024 * 1024
MIN_ENVELOPE_BYTES = 4 + MIN_PASSPHRASE_BYTES + MIN_VAULT_BYTES
MAX_ENVELOPE_BYTES = 4 + MAX_PASSPHRASE_BYTES + MAX_VAULT_BYTES

INFERENCE_TENANT = "acme"
INFERENCE_ROLE = "refund_operator"
UNLOCK_TMPFS = "/run/stoa-provider:uid=1000,gid=1000,mode=0700"
UNLOCK_SOCKET = "/run/stoa-provider/unlock.sock"

CLAUDE_MODEL = "claude-sonnet-4-6"
INFERENCE_PROMPT = "Reply with just READY."
CLAUDE_INFERENCE_CMD_DISPLAY = (
    f"$ claude --bare --print --tools '' --model {CLAUDE_MODEL} "
    f"--output-format json '{INFERENCE_PROMPT}'"
)

_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{12}$")


class InferenceDemoError(Exception):
    """Safe, redacted error for provider inference verification."""


def build_unlock_envelope(passphrase: bytes, vault_ciphertext: bytes) -> bytes:
    if not (MIN_PASSPHRASE_BYTES <= len(passphrase) <= MAX_PASSPHRASE_BYTES):
        raise InferenceDemoError("Invalid vault passphrase length.")
    if not (MIN_VAULT_BYTES <= len(vault_ciphertext) <= MAX_VAULT_BYTES):
        raise InferenceDemoError("Invalid encrypted vault size.")
    return struct.pack(">I", len(passphrase)) + passphrase + vault_ciphertext


def read_unlock_envelope(stream: BinaryIO) -> bytes:
    raw = stream.read(MAX_ENVELOPE_BYTES + 1)
    if len(raw) > MAX_ENVELOPE_BYTES or len(raw) < MIN_ENVELOPE_BYTES:
        raise InferenceDemoError("Invalid or oversized unlock envelope.")
    (pw_len,) = struct.unpack(">I", raw[:4])
    if not (MIN_PASSPHRASE_BYTES <= pw_len <= MAX_PASSPHRASE_BYTES):
        raise InferenceDemoError("Invalid unlock envelope passphrase length.")
    ct_len = len(raw) - 4 - pw_len
    if not (MIN_VAULT_BYTES <= ct_len <= MAX_VAULT_BYTES):
        raise InferenceDemoError("Invalid unlock envelope ciphertext length.")
    return raw


def generate_inference_grant() -> tuple[str, str]:
    token = secrets.token_hex(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return token, digest


def configure_inference_override(
    private_root: Path,
    cenv: dict[str, str],
    grant_sha256: str,
) -> None:
    override_path = private_root / "relay-override.json"
    if not override_path.is_file():
        raise InferenceDemoError("Compose override file missing.")
    try:
        data = json.loads(override_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InferenceDemoError("Failed to read compose override.") from exc

    if not isinstance(data, dict):
        raise InferenceDemoError("Invalid compose override structure.")
    services = data.get("services")
    if not isinstance(services, dict):
        raise InferenceDemoError("Compose override missing services mapping.")
    gw = services.get("stoa-gateway")
    if not isinstance(gw, dict):
        raise InferenceDemoError("Compose override missing stoa-gateway service.")

    tmpfs = gw.get("tmpfs")
    if tmpfs is None:
        gw["tmpfs"] = [UNLOCK_TMPFS]
    elif isinstance(tmpfs, list):
        if UNLOCK_TMPFS not in tmpfs:
            tmpfs.append(UNLOCK_TMPFS)
    else:
        raise InferenceDemoError("Unexpected tmpfs configuration in compose override.")

    ulimits = gw.get("ulimits")
    if ulimits is None:
        ulimits = {}
        gw["ulimits"] = ulimits
    elif not isinstance(ulimits, dict):
        raise InferenceDemoError("Unexpected ulimits configuration in compose override.")
    ulimits["core"] = {"soft": 0, "hard": 0}

    inf_env = {
        "STOA_LOG_FORMAT": "json",
        "RUST_LOG": "info",
        "STOA_POC_INFERENCE_GRANT_SHA256": grant_sha256,
        "STOA_POC_INFERENCE_TENANT": INFERENCE_TENANT,
        "STOA_POC_INFERENCE_ROLE": INFERENCE_ROLE,
    }
    existing_env = gw.get("environment")
    if existing_env is None:
        gw["environment"] = dict(inf_env)
    elif isinstance(existing_env, dict):
        existing_env.update(inf_env)
    else:
        raise InferenceDemoError("Unexpected environment configuration in compose override.")

    cenv.update(inf_env)

    try:
        override_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        raise InferenceDemoError("Failed to update compose override.") from exc


def gateway_inference_base_url(gateway_port: int) -> str:
    if not isinstance(gateway_port, int) or isinstance(gateway_port, bool):
        raise InferenceDemoError("Invalid loopback gateway port.")
    if not (1 <= gateway_port <= 65535):
        raise InferenceDemoError("Loopback gateway port out of range.")
    return f"http://127.0.0.1:{gateway_port}/poc/inference/anthropic"


def unlock_provider_vault(
    root: Path,
    cenv: dict[str, str],
    envelope: bytes,
    *,
    timeout: float = 30.0,
) -> None:
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "stoa-gateway",
        "curl",
        "--unix-socket",
        UNLOCK_SOCKET,
        "--silent",
        "--fail",
        "--max-time",
        "10",
        "-X",
        "POST",
        "--data-binary",
        "@-",
        "http://localhost/unlock",
    ]
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InferenceDemoError("Timed out unlocking provider vault.")
        try:
            res = subprocess.run(
                cmd,
                cwd=root,
                env=cenv,
                input=envelope,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=min(15.0, remaining),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InferenceDemoError("Failed to unlock provider vault.") from exc

        if res.returncode == 0:
            return
        if res.returncode == 7 and time.monotonic() + 0.25 < deadline:
            time.sleep(0.25)
            continue
        raise InferenceDemoError("Provider vault unlock rejected by gateway.")


def run_claude_inference(
    private_root: Path,
    claude_bin: str,
    base_url: str,
    grant_token: str,
    *,
    timeout: float = 60.0,
) -> None:
    inf_root = private_root / "claude-inference"
    inf_home = inf_root / "home"
    inf_cfg = inf_root / "config"
    inf_work = inf_root / "work"
    for directory in (inf_root, inf_home, inf_cfg, inf_work):
        os.mkdir(directory, 0o700)

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(inf_home),
        "CLAUDE_CONFIG_DIR": str(inf_cfg),
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": grant_token,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
    }
    cmd = [
        claude_bin,
        "--bare",
        "--print",
        "--tools",
        "",
        "--model",
        CLAUDE_MODEL,
        "--output-format",
        "json",
        INFERENCE_PROMPT,
    ]
    print(CLAUDE_INFERENCE_CMD_DISPLAY, flush=True)
    try:
        res = subprocess.run(
            cmd,
            cwd=inf_work,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InferenceDemoError("Claude CLI inference timed out or failed to start.") from exc

    if res.returncode != 0:
        raise InferenceDemoError("Claude CLI inference returned non-zero status.")
    if len(res.stdout) > 65536:
        raise InferenceDemoError("Claude CLI inference output exceeded size limit.")
    try:
        payload = json.loads(res.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InferenceDemoError("Claude CLI inference returned invalid JSON.") from exc

    if (
        not isinstance(payload, dict)
        or payload.get("type") != "result"
        or payload.get("subtype") != "success"
        or payload.get("is_error") is not False
    ):
        raise InferenceDemoError("Claude CLI inference did not report a successful result.")
    result_text = payload.get("result")
    if not isinstance(result_text, str) or result_text.strip() != "READY":
        raise InferenceDemoError("Claude CLI did not return expected READY response.")


def verify_gateway_inference_log(
    root: Path,
    cenv: dict[str, str],
    *,
    tail: int = 200,
    timeout: float = 15.0,
) -> str:
    cmd = [
        "docker",
        "compose",
        "logs",
        "--no-color",
        "--no-log-prefix",
        "--tail",
        str(tail),
        "stoa-gateway",
    ]
    try:
        res = subprocess.run(
            cmd,
            cwd=root,
            env=cenv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InferenceDemoError("Failed to read gateway inference logs.") from exc

    if res.returncode != 0:
        raise InferenceDemoError("Gateway log inspection failed.")
    if len(res.stdout) > 512 * 1024:
        raise InferenceDemoError("Gateway log output exceeded size limit.")

    fingerprints: set[str] = set()
    messages_seen = False
    for raw_line in res.stdout.splitlines():
        if not raw_line.startswith(b"{"):
            continue
        try:
            record = json.loads(raw_line.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
        event = fields.get("event", record.get("event"))
        if event != "poc_provider_inference":
            continue
        provider = fields.get("provider", record.get("provider"))
        kind = fields.get("kind", record.get("kind"))
        status = fields.get("upstream_status", record.get("upstream_status"))
        fp = fields.get("credential_fingerprint", record.get("credential_fingerprint"))
        if (
            provider != "anthropic"
            or kind not in ("messages", "count_tokens")
            or not isinstance(status, int)
            or isinstance(status, bool)
            or not (200 <= status < 300)
            or not isinstance(fp, str)
            or not _FINGERPRINT_RE.fullmatch(fp)
        ):
            raise InferenceDemoError("Inconsistent gateway inference log event.")
        fingerprints.add(fp)
        if kind == "messages":
            messages_seen = True

    if not messages_seen:
        raise InferenceDemoError("Gateway logs did not confirm a 2xx Anthropic messages call.")
    if len(fingerprints) != 1:
        raise InferenceDemoError("Gateway logs reported inconsistent credential fingerprints.")
    return next(iter(fingerprints))


def run_verify_inference(
    root: Path,
    private_root: Path,
    cenv: dict[str, str],
    claude_bin: str,
    envelope: bytes,
    grant_token: str,
    gateway_port: int,
) -> None:
    base_url = gateway_inference_base_url(gateway_port)
    unlock_provider_vault(root, cenv, envelope)
    run_claude_inference(private_root, claude_bin, base_url, grant_token)
    fingerprint = verify_gateway_inference_log(root, cenv)
    print(f"INFERENCE: provider=anthropic fingerprint={fingerprint} status=ok", flush=True)
