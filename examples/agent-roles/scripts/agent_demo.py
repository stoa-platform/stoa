#!/usr/bin/env python3
"""Filmable launcher for the scoped child-relay MCP agent demo."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import selectors
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agent_demo_client import (  # noqa: E402
    CALL_ARGUMENTS,
    FIRST_PROMPT,
    RETRY_PROMPT,
    STORY_ALLOW_PROMPT,
    STORY_DENY_PROMPT,
    DemoClientError,
    Receipt,
    parse_tool_result,
    run_claude,
)
from relay_smoke import (  # noqa: E402
    McpStdioClient,
    UnixHTTPConnection,
    delegate_via_control,
    prepare_runtime,
)

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
EXPECTED_JOURNAL_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "route",
        "tool",
        "rule",
        "result",
        "reason",
        "timestamp",
        "decision_id",
        "request_id",
    }
)
EXPECTED_SEQUENCE = (
    (
        "decision",
        "direct",
        "refunds_create",
        "argument_constraint",
        "denied",
        "argument_constraint_denied",
    ),
    (
        "decision",
        "direct",
        "refunds_create",
        "argument_constraint",
        "denied",
        "argument_constraint_denied",
    ),
    ("decision", "direct", "refunds_create", "admission_budget", "allowed", "ok"),
    ("execution", "direct", "refunds_create", "execution", "succeeded", "execution_succeeded"),
    ("revocation", "revoke", None, "revocation", "changed", "revoked"),
    ("decision", "direct", "refunds_create", "chain_state", "denied", "chain_revoked"),
)
EXPECTED_STATS_ONE = (
    "refund_calls",
    "upstream_calls",
    "valid_api_key_calls",
    "accepted_skill_context_calls",
)
EXPECTED_STATS_ZERO = (
    "caller_auth_headers_seen",
    "fail_calls",
    "forbidden_calls",
    "redirect_target_calls",
    "oauth2_calls",
)
EXPECTED_STATS_KEYS = frozenset(EXPECTED_STATS_ONE) | frozenset(EXPECTED_STATS_ZERO)
MAX_LINE_BYTES = 16384


class DemoError(Exception):
    """Fixed, safe, user-facing error."""


@dataclass(frozen=True)
class JournalRow:
    kind: str
    route: str
    tool: str | None
    rule: str
    result: str
    reason: str
    timestamp: str
    utc_time: str
    decision_id: str
    request_id: str


def _strict_int(val: Any) -> bool:
    return type(val) is int


def _parse_uuid(val: Any) -> str:
    if not isinstance(val, str) or not UUID_RE.fullmatch(val):
        raise DemoError("Invalid canonical lowercase UUID in gateway journal.")
    return val


def _parse_utc(val: Any) -> tuple[str, str]:
    if not isinstance(val, str) or not val:
        raise DemoError("Invalid timestamp in gateway journal.")
    raw = val[:-1] + "+00:00" if val.endswith("Z") else val
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DemoError("Invalid ISO8601 timestamp in gateway journal.") from exc
    if dt.tzinfo is None:
        raise DemoError("Gateway journal timestamp must include timezone.")
    utc_dt = dt.astimezone(UTC)
    return val, utc_dt.strftime("%H:%M:%SZ")


def _parse_journal_row(raw_line: str) -> JournalRow:
    try:
        data = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise DemoError("Malformed JSON in gateway decision journal.") from exc
    if not isinstance(data, dict) or not EXPECTED_JOURNAL_KEYS.issubset(data.keys()):
        raise DemoError("Gateway journal entry is missing required v1 schema keys.")
    if not _strict_int(data["schema_version"]) or data["schema_version"] != 1:
        raise DemoError("Unsupported gateway journal schema_version.")
    tool = data["tool"]
    if tool is not None and not isinstance(tool, str):
        raise DemoError("Invalid tool field in gateway journal.")
    for key in ("kind", "route", "rule", "result", "reason"):
        if not isinstance(data[key], str):
            raise DemoError("Invalid string field in gateway journal.")
    ts_raw, utc_time = _parse_utc(data["timestamp"])
    return JournalRow(
        kind=data["kind"],
        route=data["route"],
        tool=tool,
        rule=data["rule"],
        result=data["result"],
        reason=data["reason"],
        timestamp=ts_raw,
        utc_time=utc_time,
        decision_id=_parse_uuid(data["decision_id"]),
        request_id=_parse_uuid(data["request_id"]),
    )


def _scrub_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COMPOSE_", "STOA_POC_", "ANTHROPIC_", "CLAUDE_CODE_", "OPENAI_"))
        and k not in {"BASH_ENV", "ENV"}
    }


def _minimal_env(*, keep_term: bool = False) -> dict[str, str]:
    env: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if "TMPDIR" in os.environ:
        env["TMPDIR"] = os.environ["TMPDIR"]
    if keep_term:
        env["TERM"] = os.environ.get("TERM", "xterm-256color")
    return env


def _compose_env(private_root: Path, project: str) -> dict[str, str]:
    env = _scrub_env()
    override = private_root / "relay-override.json"
    env.update(
        {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "COMPOSE_PROJECT_NAME": project,
            "COMPOSE_FILE": f"{ROOT / 'docker-compose.yml'}{os.pathsep}{override}",
            "STOA_POC_RUNTIME_DIR": str(private_root / "fixtures"),
            "STOA_POC_BOOTSTRAP_SECRET": secrets.token_hex(32),
            "STOA_POC_UPSTREAM_API_KEY": secrets.token_hex(32),
            "STOA_POC_EXPECTED_SKILL_CONTEXT": "Refunds are simulated in EUR.",
            "STOA_POC_CHAIN_BUDGET": "2",
            "STOA_POC_CALLER_BUDGET": "3",
            "STOA_POC_DECISIONS_MAX_BYTES": "16777216",
            "STOA_POC_DECISIONS_MAX_FILES": "8",
        }
    )
    return env


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str], timeout: float, err: str) -> str:
    try:
        res = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DemoError(err) from exc
    if res.returncode != 0:
        raise DemoError(err)
    return res.stdout


def _check_local_docker() -> None:
    if os.environ.get("DOCKER_HOST", "") and not os.environ["DOCKER_HOST"].startswith("unix://"):
        raise DemoError("Remote DOCKER_HOST is not allowed; use a local Unix Docker socket.")
    if not shutil.which("docker"):
        raise DemoError("docker executable not found in PATH.")
    out = _run(
        ["docker", "context", "inspect"],
        cwd=ROOT,
        env=_scrub_env(),
        timeout=15,
        err="Docker daemon is unavailable or context inspection failed.",
    )
    try:
        ctx = json.loads(out)
    except json.JSONDecodeError as exc:
        raise DemoError("Could not parse Docker context inspection output.") from exc
    if not isinstance(ctx, list) or len(ctx) != 1 or not isinstance(ctx[0], dict):
        raise DemoError("Unexpected Docker context inspection structure.")
    host = (ctx[0].get("Endpoints") or {}).get("docker", {}).get("Host")
    if not isinstance(host, str) or not host.startswith("unix://"):
        raise DemoError("Active Docker context must use a local unix:// socket.")


def _require_stoactl() -> str:
    raw = os.environ.get("STOA_POC_STOACTL_BIN", "")
    path = Path(raw)
    if not raw or not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise DemoError("STOA_POC_STOACTL_BIN must be an absolute path to an executable stoactl.")
    return str(path)


def _require_api_key_file(raw_path: str) -> Path:
    path = Path(raw_path)
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise DemoError("API key file does not exist or cannot be accessed.") from exc
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
        raise DemoError("API key file must be a regular file owned by the current user.")
    if stat.S_IMODE(st.st_mode) & 0o077 or st.st_size == 0:
        raise DemoError("API key file must be non-empty with owner-only permissions (0600).")
    return path.resolve()


def _kill_pg(proc: subprocess.Popen[Any] | None) -> bool:
    if proc is None or proc.poll() is not None:
        return True
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return proc.poll() is not None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.1)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        return proc.poll() is not None
    return True


class Display:
    def __init__(
        self,
        private_root: Path,
        headless: bool,
        *,
        tmux_sock: Path | None = None,
        detached: bool = False,
    ) -> None:
        self.headless = headless
        self.detached = detached
        self.left_log = private_root / "left.log"
        self.right_log = private_root / "right.log"
        self.tmux_sock = tmux_sock if tmux_sock is not None else private_root / "tmux.sock"
        self._tmux_cmd = ["tmux", "-u", "-S", str(self.tmux_sock), "-f", "/dev/null"]
        self._env = _minimal_env(keep_term=True)
        self.attach_proc: subprocess.Popen[bytes] | None = None
        self.started = False

    def start(self, left_command: list[str] | None = None) -> None:
        if self.headless:
            return
        if not shutil.which("tmux") or (not self.detached and not (sys.stdin.isatty() and sys.stdout.isatty())):
            raise DemoError("Interactive mode requires tmux and a TTY (or pass --headless).")
        self.right_log.touch(mode=0o600)
        base = self._tmux_cmd
        rcmd = f"tail -n +1 -f {shlex.quote(str(self.right_log))}"
        if left_command is None:
            self.left_log.touch(mode=0o600)
            lcmd = f"tail -n +1 -f {shlex.quote(str(self.left_log))}"
            new_cmd = base + ["new-session", "-d", "-s", "stoa", "/bin/sh", "-c", lcmd]
            split_cmd = base + ["split-window", "-h", "-t", "stoa", "/bin/sh", "-c", rcmd]
        else:
            new_cmd = base + ["new-session", "-d", "-s", "stoa", *left_command]
            split_cmd = base + ["split-window", "-d", "-h", "-t", "stoa", "/bin/sh", "-c", rcmd]
        _run(
            new_cmd,
            cwd=ROOT,
            env=self._env,
            timeout=10,
            err="Failed to start tmux session.",
        )
        self.started = True
        _run(
            base + ["set-option", "-t", "stoa", "status", "off"],
            cwd=ROOT,
            env=self._env,
            timeout=10,
            err="Failed to configure tmux session.",
        )
        _run(
            split_cmd,
            cwd=ROOT,
            env=self._env,
            timeout=10,
            err="Failed to split tmux panes.",
        )
        if not self.detached:
            self.attach_proc = subprocess.Popen(
                base + ["attach-session", "-t", "stoa"], env=self._env, stderr=subprocess.DEVNULL
            )

    def tmux(self, args: list[str]) -> str:
        if self.headless or not self.started:
            raise DemoError("tmux is only available in interactive mode.")
        return _run(
            self._tmux_cmd + args,
            cwd=ROOT,
            env=self._env,
            timeout=10,
            err="tmux command failed.",
        )

    def left(self, line: str) -> None:
        if self.headless:
            print(f"[agent] {line}", flush=True)
        else:
            with open(self.left_log, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def right(self, line: str) -> None:
        if self.headless:
            print(f"[gateway] {line}", flush=True)
        else:
            with open(self.right_log, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def hold(self, seconds: float = 4.0) -> None:
        if self.headless or not self.started:
            return
        end = time.monotonic() + seconds
        if self.attach_proc is not None:
            while time.monotonic() < end and self.attach_proc.poll() is None:
                time.sleep(0.2)
            return
        if not self.detached:
            return
        while time.monotonic() < end:
            time.sleep(0.2)

    def close(self) -> bool:
        ok = True
        if self.started:
            try:
                subprocess.run(
                    [*self._tmux_cmd, "kill-server"],
                    env=self._env,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                ok = False
            self.started = False
        if self.tmux_sock.exists():
            try:
                self.tmux_sock.unlink()
            except OSError:
                ok = False
        if self.attach_proc is not None and self.attach_proc.poll() is None:
            try:
                self.attach_proc.terminate()
                self.attach_proc.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.attach_proc.kill()
                    self.attach_proc.wait(timeout=2.0)
                except (OSError, subprocess.TimeoutExpired):
                    ok = False
        return ok


def _create_grant_socket(path: Path) -> socket.socket:
    if path.exists():
        path.unlink()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(str(path))
        os.chmod(path, 0o600)
        srv.listen(1)
    except OSError as exc:
        srv.close()
        path.unlink(missing_ok=True)
        raise DemoError("Failed to create private grant socket.") from exc
    return srv


def _deliver_grant_once(srv: socket.socket, path: Path, grant: str, timeout: float = 15.0) -> None:
    grant_bytes = grant.encode("ascii")
    if len(grant_bytes) != 64:
        raise DemoError("Unexpected inference grant length.")
    conn: socket.socket | None = None
    try:
        srv.settimeout(timeout)
        conn, _ = srv.accept()
        conn.settimeout(5.0)
        conn.sendall(grant_bytes)
    except OSError as exc:
        raise DemoError("Failed to deliver inference grant over private socket.") from exc
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        srv.close()
        path.unlink(missing_ok=True)


class JournalFollower:
    def __init__(self, env: dict[str, str]) -> None:
        self.proc = subprocess.Popen(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "stoa-gateway",
                "tail",
                "-n",
                "+1",
                "-F",
                "/tmp/stoa-poc-floors/decisions/decisions.ndjson",
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        assert self.proc.stdout is not None
        self._fd = self.proc.stdout.fileno()
        os.set_blocking(self._fd, False)
        self._sel = selectors.DefaultSelector()
        self._sel.register(self._fd, selectors.EVENT_READ)
        self._buf = bytearray()
        self._lines: list[str] = []

    def next_row(self, timeout: float = 20.0) -> JournalRow:
        deadline = time.monotonic() + timeout
        while True:
            if self._lines:
                return _parse_journal_row(self._lines.pop(0))
            rem = deadline - time.monotonic()
            if rem <= 0:
                raise DemoError("Timed out waiting for gateway journal event.")
            if not self._sel.select(timeout=min(rem, 0.25)):
                if self.proc.poll() is not None:
                    raise DemoError("Gateway journal stream exited unexpectedly.")
                continue
            try:
                chunk = os.read(self._fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                raise DemoError("Gateway journal stream closed unexpectedly.")
            self._buf.extend(chunk)
            if len(self._buf) > MAX_LINE_BYTES * 4:
                raise DemoError("Gateway journal output exceeded safety bound.")
            while b"\n" in self._buf:
                idx = self._buf.index(b"\n")
                if idx > MAX_LINE_BYTES:
                    raise DemoError("Gateway journal line exceeded safety bound.")
                raw = bytes(self._buf[:idx]).decode("utf-8", errors="strict").strip()
                del self._buf[: idx + 1]
                if raw:
                    self._lines.append(raw)

    def close(self) -> bool:
        self._sel.close()
        return _kill_pg(self.proc)


def _constraint_label(receipt: Any) -> str:
    if receipt.reason == "ok":
        return "allowed"
    if receipt.reason == "chain_revoked":
        return "chain revoked"
    if receipt.constraint == "amount_exceeds_cap" and _strict_int(receipt.limit_eur):
        return f"amount > €{receipt.limit_eur}"
    if receipt.constraint == "customer_outside_scope":
        return "customer outside scope"
    raise DemoError("Unrecognized constraint in tool receipt.")


def _revoke_control(control_sock: Path) -> None:
    conn = UnixHTTPConnection(str(control_sock), timeout=10.0)
    try:
        conn.request(
            "POST", "/v1/revoke-chain", body=b"{}", headers={"Content-Type": "application/json"}
        )
        resp = conn.getresponse()
        body = resp.read(4096)
    except OSError as exc:
        raise DemoError("Failed to call relay revoke-chain endpoint.") from exc
    finally:
        conn.close()
    if resp.status != 200:
        raise DemoError("Relay revoke-chain endpoint returned non-200 status.")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoError("Invalid JSON from relay revoke-chain endpoint.") from exc
    if parsed != {"gateway_chain_revoked": True}:
        raise DemoError("Gateway chain revocation was not confirmed.")


def _verify_export(private_root: Path, env: dict[str, str], expected: list[JournalRow]) -> None:
    export_dir = private_root / "export"
    os.mkdir(export_dir, 0o700)
    _run(
        [str(ROOT / "scripts" / "export_decisions.sh"), str(export_dir)],
        cwd=ROOT,
        env=env,
        timeout=30,
        err="Locked decision export verification failed.",
    )
    health_path = export_dir / "decisions.health.json"
    ndjson_path = export_dir / "decisions.ndjson"
    if not health_path.is_file() or not ndjson_path.is_file():
        raise DemoError("Expected exported decisions.ndjson or decisions.health.json is missing.")
    try:
        health = json.loads(health_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoError("Exported decisions.health.json is invalid.") from exc
    if (
        not isinstance(health, dict)
        or health.get("status") != "healthy"
        or health.get("gap_detected") is not False
    ):
        raise DemoError("Exported journal health check failed.")
    exported = [
        _parse_journal_row(line.strip())
        for line in ndjson_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if exported != expected:
        raise DemoError("Exported journal rows do not match observed run.")


def _verify_upstream_stats(env: dict[str, str]) -> int:
    out = _run(
        ["docker", "compose", "exec", "-T", "upstream-mock", "cat", "/tmp/upstream_stats.json"],
        cwd=ROOT,
        env=env,
        timeout=15,
        err="Failed to read upstream mock stats.",
    )
    try:
        stats = json.loads(out)
    except json.JSONDecodeError as exc:
        raise DemoError("Upstream mock stats are not valid JSON.") from exc
    if not isinstance(stats, dict) or set(stats.keys()) != EXPECTED_STATS_KEYS:
        raise DemoError("Upstream mock stats keys do not match expected schema.")
    for key in EXPECTED_STATS_ONE:
        if not _strict_int(stats[key]) or stats[key] != 1:
            raise DemoError("Upstream mock verification failed on expected call counters.")
    for key in EXPECTED_STATS_ZERO:
        if not _strict_int(stats[key]) or stats[key] != 0:
            raise DemoError("Upstream mock reported unexpected non-zero counter.")
    return stats["caller_auth_headers_seen"]


def _row_tuple(row: JournalRow) -> tuple[Any, ...]:
    return (row.kind, row.route, row.tool, row.rule, row.result, row.reason)


def _run_verify_install(
    private_root: Path,
    cenv: dict[str, str],
    stoactl_bin: str,
    child_sock: str,
    claude_bin: str,
    journal: JournalFollower,
) -> None:
    print(
        "INIT: gateway=ready parent_cap=500 EUR (Ed25519 signed) child_cap=50 EUR customer=C-1042",
        flush=True,
    )
    claude_profile = private_root / "claude-profile"
    claude_cwd = private_root / "work"
    os.mkdir(claude_profile, 0o700)
    os.mkdir(claude_cwd, 0o700)

    claude_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(claude_profile),
        "CLAUDE_CONFIG_DIR": str(claude_profile),
        "LC_ALL": "C",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
    }
    print(
        '$ claude mcp add --scope local refunds -- "$STOACTL" relay connect --socket "$RELAY_SOCKET"',
        flush=True,
    )
    _run(
        [
            claude_bin,
            "mcp",
            "add",
            "--scope",
            "local",
            "refunds",
            "--",
            stoactl_bin,
            "relay",
            "connect",
            "--socket",
            child_sock,
        ],
        cwd=claude_cwd,
        env=claude_env,
        timeout=30,
        err="Failed to register local MCP server with Claude CLI.",
    )

    cfg_path = claude_profile / ".claude.json"
    try:
        st = os.lstat(cfg_path)
    except OSError as exc:
        raise DemoError("Claude CLI did not write local .claude.json configuration.") from exc
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid != os.getuid()
        or stat.S_IMODE(st.st_mode) != 0o600
    ):
        raise DemoError("Claude CLI .claude.json failed file security checks.")
    try:
        cfg_bytes = cfg_path.read_bytes()
        cfg = json.loads(cfg_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoError("Could not parse Claude CLI .claude.json configuration.") from exc
    projects = cfg.get("projects") if isinstance(cfg, dict) else None
    if not isinstance(projects, dict):
        raise DemoError("Claude CLI .claude.json is missing projects mapping.")
    proj = projects.get(str(claude_cwd.resolve()))
    if proj is None:
        proj = projects.get(str(claude_cwd))
    mcp_servers = proj.get("mcpServers") if isinstance(proj, dict) else None
    if not isinstance(mcp_servers, dict) or list(mcp_servers.keys()) != ["refunds"]:
        raise DemoError("Claude CLI .claude.json must contain exactly one refunds MCP server.")
    entry = mcp_servers["refunds"]
    expected_args = ["relay", "connect", "--socket", child_sock]
    if (
        not isinstance(entry, dict)
        or not set(entry.keys()).issubset({"type", "command", "args", "env"})
        or entry.get("type") != "stdio"
        or entry.get("command") != stoactl_bin
        or entry.get("args") != expected_args
        or entry.get("env", {}) != {}
    ):
        raise DemoError("Claude CLI .claude.json refunds MCP entry did not match expected config.")

    print(
        "MCP_PROBE: direct MCP stdio probe reading real Claude CLI local config "
        "(no model inference; no vault keys forwarded)",
        flush=True,
    )
    observed: list[JournalRow] = []
    try:
        with McpStdioClient(
            entry["command"], entry["args"][3], private_root / "agent-home", "relay"
        ) as client:
            client.initialize()
            if "refunds_create" not in client.tools_list():
                raise DemoError("Relay tools/list did not expose refunds_create.")

            rpc_allow = client.tools_call("refunds_create", CALL_ARGUMENTS[2])
            if (
                not isinstance(rpc_allow, dict)
                or "error" in rpc_allow
                or not isinstance(rpc_allow.get("result"), dict)
            ):
                raise DemoError("Allowed refund tools/call returned invalid envelope.")
            res_allow: Receipt = parse_tool_result(2, rpc_allow["result"])
            row_allow = journal.next_row(timeout=15.0)
            row_exec = journal.next_row(timeout=15.0)
            if (
                _row_tuple(row_allow) != EXPECTED_SEQUENCE[2]
                or _row_tuple(row_exec) != EXPECTED_SEQUENCE[3]
            ):
                raise DemoError("Observed journal rows for allowed call did not match expected sequence.")
            if (
                res_allow.reason != row_allow.reason
                or row_allow.decision_id != row_exec.decision_id
                or row_allow.request_id != row_exec.request_id
            ):
                raise DemoError("Allowed and execution journal rows failed ID pairing check.")
            observed.extend([row_allow, row_exec])
            amt_allow = CALL_ARGUMENTS[2]["amount_eur"]
            print(
                f"CALL 1 (EUR {amt_allow}): allowed | decision_id={row_allow.decision_id} | {res_allow.message}",
                flush=True,
            )
            print(
                f"JOURNAL: decision=allowed decision_id={row_allow.decision_id} | "
                f"execution=succeeded decision_id={row_exec.decision_id}",
                flush=True,
            )

            rpc_deny = client.tools_call("refunds_create", CALL_ARGUMENTS[0])
            if (
                not isinstance(rpc_deny, dict)
                or "error" in rpc_deny
                or not isinstance(rpc_deny.get("result"), dict)
            ):
                raise DemoError("Denied refund tools/call returned invalid envelope.")
            res_deny: Receipt = parse_tool_result(0, rpc_deny["result"])
            row_deny = journal.next_row(timeout=15.0)
            if _row_tuple(row_deny) != EXPECTED_SEQUENCE[0]:
                raise DemoError("Observed journal row for denied call did not match expected sequence.")
            if (
                res_deny.decision_id != row_deny.decision_id
                or res_deny.reason != row_deny.reason
                or row_deny.decision_id == row_allow.decision_id
                or row_deny.request_id == row_allow.request_id
            ):
                raise DemoError("Denied tool result did not match journal decision row.")
            observed.append(row_deny)
            amt_deny = CALL_ARGUMENTS[0]["amount_eur"]
            print(
                f"CALL 2 (EUR {amt_deny}): refused | decision_id={res_deny.decision_id} | "
                f"reason={res_deny.reason} | constraint={res_deny.constraint} | "
                f"limit_eur={res_deny.limit_eur} | {res_deny.message}",
                flush=True,
            )
            print(
                f"JOURNAL: decision=denied reason={row_deny.reason} decision_id={row_deny.decision_id}",
                flush=True,
            )
    except DemoError:
        raise
    except Exception as exc:
        raise DemoError("Install MCP probe verification failed.") from exc

    if cfg_path.read_bytes() != cfg_bytes:
        raise DemoError("Claude CLI .claude.json changed during MCP probe.")
    _verify_export(private_root, cenv, observed)
    print("EXPORT: locked journal verified (3 rows)", flush=True)
    auth_headers_seen = _verify_upstream_stats(cenv)
    print(f"UPSTREAM: caller_auth_headers_seen={auth_headers_seen}", flush=True)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise DemoError("Invalid command-line arguments.")


STORY_CLIENTS = ("claude", "vibe", "antigravity", "codex")
STORY_MODEL = "claude-sonnet-4-6"


def _require_story_home(raw_path: str) -> Path:
    path = Path(raw_path)
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise DemoError("Story HOME directory is unavailable.") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise DemoError("Story HOME must be a real directory.")
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise DemoError("Story HOME must be an owner-only (0700) directory.")
    resolved = path.resolve()
    if resolved == Path.home().resolve():
        raise DemoError("Story HOME must be a disposable directory.")
    return resolved


def _run_verify_story(
    private_root: Path,
    cenv: dict[str, str],
    stoactl_bin: str,
    child_sock: str,
    claude_bin: str,
    story_home: Path,
    gateway_port: int,
    inference_envelope: bytes,
    inference_grant: str,
    journal: JournalFollower,
    *,
    display: Display | None = None,
    story_split: bool = False,
    expected_fingerprint: str | None = None,
    t0: float | None = None,
) -> None:
    from provider_inference_demo import (
        InferenceDemoError,
        gateway_inference_base_url,
        unlock_provider_vault,
        verify_gateway_inference_log,
    )

    if story_split and display is None:
        raise DemoError("Split story mode requires a display.")

    print("=== stoactl plugs the agents into the gateway. ===", flush=True)
    if story_split and display is not None:
        display.right("=== stoactl plugs the agents into the gateway. ===")
    connect_env = _minimal_env()
    connect_env["HOME"] = str(story_home)
    for client in STORY_CLIENTS:
        work_dir = story_home / f"work-{client}"
        if not work_dir.exists():
            os.mkdir(work_dir, 0o700)
        _run(
            [
                stoactl_bin,
                "connect",
                "--client",
                client,
                "--from-home",
                str(story_home),
                "--workspace",
                str(work_dir),
                "--socket",
                child_sock,
                "--gateway-port",
                str(gateway_port),
                "--stoactl",
                stoactl_bin,
            ],
            cwd=work_dir,
            env=connect_env,
            timeout=30,
            err=f"stoactl connect failed for {client}.",
        )
        print(f"CONNECT {client}: attached", flush=True)
        if story_split and display is not None:
            display.right(f"CONNECT {client}: attached")

    try:
        unlock_provider_vault(ROOT, cenv, inference_envelope)
    except InferenceDemoError as exc:
        raise DemoError(str(exc)) from exc

    print("=== Same agents, now governed. ===", flush=True)
    if story_split and display is not None:
        display.right("")
        display.right("=== Same agents, now governed. ===")
    claude_work = story_home / "work-claude"
    mcp_cfg = claude_work / ".mcp.json"
    if not mcp_cfg.is_file():
        raise DemoError("Connector did not write work-claude/.mcp.json.")
    gateway_settings = story_home / ".claude" / "settings.gateway.json"
    settings_arg = gateway_settings if gateway_settings.is_file() else None
    claude_profile = story_home / ".claude"
    if not claude_profile.exists():
        os.mkdir(claude_profile, 0o700)

    observed: list[JournalRow] = []
    allow_row: JournalRow | None = None

    def on_story_result(idx: int, receipt: Receipt) -> None:
        nonlocal allow_row
        if idx == 2:
            row_allow = journal.next_row(timeout=15.0)
            row_exec = journal.next_row(timeout=15.0)
            if (
                _row_tuple(row_allow) != EXPECTED_SEQUENCE[2]
                or _row_tuple(row_exec) != EXPECTED_SEQUENCE[3]
            ):
                raise DemoError(
                    "Observed journal rows for allowed call did not match expected sequence."
                )
            if (
                receipt.reason != row_allow.reason
                or row_allow.decision_id != row_exec.decision_id
                or row_allow.request_id != row_exec.request_id
            ):
                raise DemoError("Allowed and execution journal rows failed ID pairing check.")
            if story_split and (
                receipt.decision_id != row_allow.decision_id
                or receipt.decision_id != row_exec.decision_id
            ):
                raise DemoError("Allowed tool receipt UUID did not match journal decision and execution rows.")
            allow_row = row_allow
            observed.extend([row_allow, row_exec])
            amt_allow = CALL_ARGUMENTS[2]["amount_eur"]
            print(
                f"CALL 1 (EUR {amt_allow}): allowed | decision_id={row_allow.decision_id} | {receipt.message}",
                flush=True,
            )
            print(
                f"JOURNAL: decision=allowed decision_id={row_allow.decision_id} | "
                f"execution=succeeded decision_id={row_exec.decision_id}",
                flush=True,
            )
            if story_split and display is not None:
                display.right(
                    f"{row_allow.utc_time} | {row_allow.tool} | {row_allow.result} | decision_id={row_allow.decision_id}"
                )
                display.right(
                    f"{row_exec.utc_time} | {row_exec.tool} | {row_exec.result} | decision_id={row_exec.decision_id}"
                )
        elif idx == 0:
            if allow_row is None:
                raise DemoError("Refusal observed before allowed refund call.")
            row_deny = journal.next_row(timeout=15.0)
            if _row_tuple(row_deny) != EXPECTED_SEQUENCE[0]:
                raise DemoError(
                    "Observed journal row for denied call did not match expected sequence."
                )
            if (
                receipt.decision_id != row_deny.decision_id
                or receipt.reason != row_deny.reason
                or row_deny.decision_id == allow_row.decision_id
                or row_deny.request_id == allow_row.request_id
            ):
                raise DemoError("Denied tool result did not match journal decision row.")
            observed.append(row_deny)
            amt_deny = CALL_ARGUMENTS[0]["amount_eur"]
            print(
                f"CALL 2 (EUR {amt_deny}): refused | decision_id={receipt.decision_id} | "
                f"reason={receipt.reason} | constraint={receipt.constraint} | "
                f"limit_eur={receipt.limit_eur} | {receipt.message}",
                flush=True,
            )
            print(
                f"JOURNAL: decision=denied reason={row_deny.reason} decision_id={row_deny.decision_id}",
                flush=True,
            )
            if story_split and display is not None:
                display.right(
                    f"{row_deny.utc_time} | {row_deny.tool} | {row_deny.result} | decision_id={row_deny.decision_id}"
                )
                display.right(
                    f"reason={row_deny.reason} | constraint={receipt.constraint} | limit_eur={receipt.limit_eur} EUR"
                )
        else:
            raise DemoError("Unexpected tool call index in story verification.")

    try:
        if story_split:
            import json
            from agent_demo_tui import governed_tui_command, run_tui

            assert display is not None
            raw_mcp = json.loads(mcp_cfg.read_text(encoding="utf-8"))
            servers = raw_mcp.get("mcpServers") if isinstance(raw_mcp, dict) else None
            if not isinstance(servers, dict) or not servers:
                raise DemoError("Invalid MCP config for split TUI.")
            for srv_cfg in servers.values():
                if not isinstance(srv_cfg, dict):
                    raise DemoError("Invalid MCP server entry for split TUI.")
                srv_cfg["alwaysLoad"] = True
            split_mcp_cfg = private_root / "split-mcp-config.json"
            split_mcp_cfg.write_text(json.dumps(raw_mcp), encoding="utf-8")
            session_id = str(uuid.uuid4())
            grant_sock = private_root / "grant.sock"
            grant_srv = _create_grant_socket(grant_sock)
            try:
                left_cmd = governed_tui_command(
                    claude_bin,
                    claude_profile,
                    claude_work,
                    split_mcp_cfg,
                    settings_arg,
                    grant_sock,
                    session_id,
                    gateway_inference_base_url(gateway_port),
                )
                display.start(left_command=left_cmd)
                _deliver_grant_once(grant_srv, grant_sock, inference_grant, timeout=15.0)
            except BaseException:
                grant_srv.close()
                grant_sock.unlink(missing_ok=True)
                raise
            print("SPLIT_READY", flush=True)
            attach_deadline = time.monotonic() + 15.0
            while time.monotonic() < attach_deadline:
                attached = display.tmux(
                    ["display-message", "-p", "-t", "stoa", "#{session_attached}"]
                ).strip()
                if attached.isdigit() and int(attached) >= 1:
                    break
                time.sleep(0.1)
            else:
                raise DemoError("Timed out waiting for split tmux session attachment.")
            run_tui(
                tmux=display.tmux,
                profile=claude_profile,
                session_id=session_id,
                deadline=time.monotonic() + 180.0,
                on_result=on_story_result,
                revoke=lambda: None,
                turns=((STORY_ALLOW_PROMPT, (2,)), (STORY_DENY_PROMPT, (0,))),
            )
        else:
            run_claude(
                executable=claude_bin,
                profile=claude_profile,
                cwd=claude_work,
                mcp_config=mcp_cfg,
                api_key_file=None,
                deadline=time.monotonic() + 180.0,
                on_prompt=lambda _prompt: None,
                on_result=on_story_result,
                revoke=None,
                home_dir=story_home,
                settings_file=settings_arg,
                model=STORY_MODEL,
                anthropic_base_url=gateway_inference_base_url(gateway_port),
                anthropic_auth_token=inference_grant,
                turns=((STORY_ALLOW_PROMPT, (2,)), (STORY_DENY_PROMPT, (0,))),
            )
    except DemoClientError as exc:
        raise DemoError("Claude Code story scenario did not complete all verified steps.") from exc

    if len(observed) != 3:
        raise DemoError("Story scenario did not record all three expected journal rows.")
    _verify_export(private_root, cenv, observed)
    print("EXPORT: locked journal verified (3 rows)", flush=True)
    auth_headers_seen = _verify_upstream_stats(cenv)
    print(f"UPSTREAM: caller_auth_headers_seen={auth_headers_seen}", flush=True)
    try:
        fingerprint = verify_gateway_inference_log(ROOT, cenv)
    except InferenceDemoError as exc:
        raise DemoError(str(exc)) from exc
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise DemoError("Gateway inference fingerprint did not match expected credential.")
    print(f"INFERENCE: provider=anthropic fingerprint={fingerprint} status=ok", flush=True)
    if story_split and display is not None:
        decision_ids = sorted({row.decision_id for row in observed if row.decision_id})
        if len(decision_ids) != 2:
            raise DemoError(
                "Story scenario did not record two distinct verified decision IDs."
            )
        left_text = display.tmux(["capture-pane", "-p", "-J", "-t", "stoa:0.0"])
        if not all(decision_id in left_text for decision_id in decision_ids):
            display.tmux(["send-keys", "-t", "stoa:0.0", "C-o"])
            left_deadline = time.monotonic() + 6.0
            while True:
                attached = display.tmux(
                    ["display-message", "-p", "-t", "stoa", "#{session_attached}"]
                ).strip()
                if not attached or attached == "0":
                    raise DemoError("Split display session detached before completion.")
                left_text = display.tmux(["capture-pane", "-p", "-J", "-t", "stoa:0.0"])
                if all(decision_id in left_text for decision_id in decision_ids):
                    break
                if time.monotonic() >= left_deadline:
                    raise DemoError(
                        "Timed out waiting for verified decision IDs to appear in left pane."
                    )
                time.sleep(0.05)
        elapsed = time.monotonic() - t0 if t0 is not None else 0.0
        display.right("")
        display.right("PROOF: 2 verified decisions + 1 paired execution (3 rows)")
        display.right(
            f"ELAPSED: {elapsed:.2f}s (startup + scenario; excludes hold and teardown)"
        )
        upstream_line = f"UPSTREAM: caller_auth_headers_seen={auth_headers_seen}"
        display.right(upstream_line)
        deadline = time.monotonic() + 3.0
        while True:
            attached_res = display.tmux(
                ["display-message", "-p", "-t", "stoa", "#{session_attached}"]
            )
            attached = getattr(attached_res, "stdout", attached_res).strip()
            if not attached or attached == "0":
                raise DemoError("Split display session detached before completion.")
            pane_res = display.tmux(["capture-pane", "-p", "-J", "-t", "stoa:0.1"])
            pane_text = getattr(pane_res, "stdout", pane_res)
            if any(line.strip() == upstream_line for line in pane_text.splitlines()):
                break
            if time.monotonic() >= deadline:
                raise DemoError("Timed out waiting for split display output.")
            time.sleep(0.05)
        display.hold(4.0)


def _handle_sigterm(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt()


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    parser = _SafeArgumentParser(description="Scoped child-relay MCP agent demo launcher.")
    parser.add_argument("--prepare", action="store_true", help="Build tagged local demo images.")
    parser.add_argument("--api-key-file", help="Path to owner-only (0600) API key file.")
    parser.add_argument("--headless", action="store_true", help="Run without tmux.")
    parser.add_argument(
        "--verify-relay", action="store_true", help="Credential-free MCP relay plumbing check."
    )
    parser.add_argument(
        "--verify-install",
        action="store_true",
        help="Verify local Claude CLI MCP registration and direct relay probe (requires --headless).",
    )
    parser.add_argument(
        "--verify-inference",
        action="store_true",
        help="Run live Anthropic inference through the isolated gateway (requires --verify-install --headless).",
    )
    parser.add_argument(
        "--verify-story",
        action="store_true",
        help="Run chapters 4-5 governed story with stoactl connect and live Claude CLI (requires --story-home and --headless or --story-split).",
    )
    parser.add_argument(
        "--story-split",
        action="store_true",
        help="Internal: run chapters 4-5 story in detached split tmux mode (requires --verify-story, excludes --headless).",
    )
    parser.add_argument(
        "--story-home",
        help="Path to disposable owner-only (0700) story HOME directory (requires --verify-story).",
    )
    parser.add_argument(
        "--expected-fingerprint",
        help="Optional 12-hex expected provider credential fingerprint for verification before split summary.",
    )
    args = parser.parse_args(argv)

    _check_local_docker()
    if args.prepare:
        if (
            args.api_key_file
            or args.verify_relay
            or args.verify_install
            or args.verify_inference
            or args.verify_story
            or args.story_home
            or args.story_split
            or args.expected_fingerprint
        ):
            raise DemoError("--prepare must be run by itself.")
        _run(
            [str(ROOT / "scripts" / "run_relay.sh"), "--prepare"],
            cwd=ROOT,
            env=_scrub_env(),
            timeout=1800,
            err="Image preparation failed.",
        )
        print("Prepared tagged local demo images.")
        return 0

    if args.verify_inference:
        if not (args.verify_install and args.headless):
            raise DemoError("--verify-inference requires --verify-install and --headless.")
        if args.verify_relay or args.api_key_file:
            raise DemoError("--verify-inference cannot be combined with --verify-relay or --api-key-file.")
    if args.verify_install:
        if not args.headless:
            raise DemoError("--verify-install requires --headless.")
        if args.verify_relay or args.api_key_file:
            raise DemoError("--verify-install cannot be combined with --verify-relay or --api-key-file.")
    if args.verify_story:
        if args.story_split:
            if args.headless:
                raise DemoError("--story-split cannot be combined with --headless.")
        elif not args.headless:
            raise DemoError("--verify-story requires --headless or --story-split.")
        if not args.story_home:
            raise DemoError("--verify-story requires --story-home.")
        if args.verify_install or args.verify_inference or args.verify_relay or args.api_key_file:
            raise DemoError(
                "--verify-story cannot be combined with --verify-install, --verify-inference, --verify-relay, or --api-key-file."
            )
    elif args.story_home:
        raise DemoError("--story-home requires --verify-story.")
    if args.story_split and not args.verify_story:
        raise DemoError("--story-split requires --verify-story.")
    if args.expected_fingerprint:
        if not args.verify_story:
            raise DemoError("--expected-fingerprint requires --verify-story.")
        if not re.fullmatch(r"[0-9a-f]{12}", args.expected_fingerprint):
            raise DemoError("Invalid --expected-fingerprint format.")
    if args.verify_relay and args.api_key_file:
        raise DemoError("--verify-relay and --api-key-file cannot be combined.")

    story_home_path: Path | None = _require_story_home(args.story_home) if args.verify_story else None
    inference_envelope: bytes | None = None
    inference_grant: str | None = None
    inference_grant_sha256: str | None = None
    if args.verify_inference or args.verify_story:
        from provider_inference_demo import (
            InferenceDemoError,
            configure_inference_override,
            generate_inference_grant,
            read_unlock_envelope,
            run_verify_inference,
        )
        try:
            inference_envelope = read_unlock_envelope(sys.stdin.buffer)
        except InferenceDemoError as exc:
            raise DemoError(str(exc)) from exc
        inference_grant, inference_grant_sha256 = generate_inference_grant()
    stoactl_bin = _require_stoactl()
    api_key_path: Path | None = None
    claude_bin: str | None = None
    if args.verify_install or args.verify_story:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise DemoError("claude CLI executable not found in PATH.")
    elif not args.verify_relay:
        if not args.api_key_file:
            raise DemoError("--api-key-file is required unless --verify-relay is specified.")
        api_key_path = _require_api_key_file(args.api_key_file)
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise DemoError("claude CLI executable not found in PATH.")

    private_root = Path(tempfile.mkdtemp(prefix="stoa-", dir="/tmp")).resolve()
    project = f"stoa-demo-{secrets.token_hex(6)}"
    cenv = _compose_env(private_root, project)
    compose_attempted = False
    relay_proc: subprocess.Popen[bytes] | None = None
    journal: JournalFollower | None = None
    split_tmux_sock = story_home_path.parent / "split.sock" if (args.story_split and story_home_path is not None) else None
    display = Display(
        private_root,
        headless=args.headless,
        tmux_sock=split_tmux_sock,
        detached=bool(args.story_split),
    )
    teardown_failed = False

    try:
        t0 = time.monotonic()
        try:
            gateway_port = prepare_runtime(private_root, None)
        except Exception as exc:
            raise DemoError("Failed to initialize isolated relay runtime.") from exc

        if args.verify_inference or args.verify_story:
            assert inference_grant_sha256 is not None
            try:
                configure_inference_override(private_root, cenv, inference_grant_sha256)
            except InferenceDemoError as exc:
                raise DemoError(str(exc)) from exc

        relay_cfg = private_root / "op" / "relay-config.json"
        control_sock = private_root / "op" / "control.sock"
        parent_sock = private_root / "mcp" / "parent.sock"
        cfg = json.loads(relay_cfg.read_text(encoding="utf-8"))
        cfg["project_decision_evidence"] = True
        relay_cfg.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        _run(
            [
                sys.executable,
                str(ROOT / "scripts" / "gen_fixtures.py"),
                str(private_root / "fixtures"),
                "--refund-demo",
            ],
            cwd=ROOT,
            env=cenv,
            timeout=30,
            err="Failed to generate refund demo fixtures.",
        )
        compose_attempted = True
        _run(
            [
                "docker",
                "compose",
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "stoa-gateway",
                "upstream-mock",
            ],
            cwd=ROOT,
            env=cenv,
            timeout=90,
            err="Failed to start isolated gateway and upstream mock.",
        )

        relay_proc = subprocess.Popen(
            [stoactl_bin, "relay", "serve", "--skip-profile-advisory", "--config", str(relay_cfg)],
            cwd=private_root,
            env=_minimal_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if relay_proc.poll() is not None:
                raise DemoError("Relay daemon exited unexpectedly during startup.")
            if control_sock.exists() and parent_sock.exists():
                break
            time.sleep(0.1)
        else:
            raise DemoError("Timed out waiting for relay sockets.")

        try:
            deleg = delegate_via_control(str(control_sock), private_root / "ch", str(parent_sock))
        except Exception as exc:
            raise DemoError("Failed to delegate child relay session.") from exc
        child_sock = deleg.get("socket_path") if isinstance(deleg, dict) else None
        if not isinstance(child_sock, str) or not Path(child_sock).exists():
            raise DemoError("Delegation did not return a valid child socket.")

        if args.verify_story:
            assert (
                claude_bin is not None
                and story_home_path is not None
                and inference_envelope is not None
                and inference_grant is not None
            )
            journal = JournalFollower(cenv)
            _run_verify_story(
                private_root,
                cenv,
                stoactl_bin,
                child_sock,
                claude_bin,
                story_home_path,
                gateway_port,
                inference_envelope,
                inference_grant,
                journal,
                display=display,
                story_split=bool(args.story_split),
                expected_fingerprint=args.expected_fingerprint,
                t0=t0,
            )
            return 0

        if args.verify_install:
            assert claude_bin is not None
            journal = JournalFollower(cenv)
            _run_verify_install(private_root, cenv, stoactl_bin, child_sock, claude_bin, journal)
            if args.verify_inference:
                assert inference_envelope is not None and inference_grant is not None
                try:
                    run_verify_inference(
                        ROOT,
                        private_root,
                        cenv,
                        claude_bin,
                        inference_envelope,
                        inference_grant,
                        gateway_port,
                    )
                except InferenceDemoError as exc:
                    raise DemoError(str(exc)) from exc
            return 0

        native_tui = not args.verify_relay and not args.headless
        refunds_server: dict[str, Any] = {
            "type": "stdio",
            "command": stoactl_bin,
            "args": ["relay", "connect", "--socket", child_sock],
        }
        if native_tui:
            refunds_server["alwaysLoad"] = True
        mcp_cfg = private_root / "mcp-config.json"
        mcp_cfg.write_text(
            json.dumps({"mcpServers": {"refunds": refunds_server}}),
            encoding="utf-8",
        )
        claude_profile = private_root / "claude-profile"
        claude_cwd = private_root / "work"
        os.mkdir(claude_profile, 0o700)
        os.mkdir(claude_cwd, 0o700)

        session_id: str | None = None
        journal = JournalFollower(cenv)
        if native_tui:
            from agent_demo_tui import run_tui, tui_launch_command

            assert claude_bin is not None and api_key_path is not None
            session_id = str(uuid.uuid4())
            display.start(
                left_command=tui_launch_command(
                    executable=claude_bin,
                    profile=claude_profile,
                    cwd=claude_cwd,
                    mcp_config=mcp_cfg,
                    api_key_file=api_key_path,
                    session_id=session_id,
                )
            )
        else:
            display.start()
            display.left(
                "[VERIFY-RELAY] Credential-free MCP plumbing check (not a model run)"
                if args.verify_relay
                else "[CLAUDE CODE] Scoped child relay MCP demo"
            )
        display.right("[GATEWAY JOURNAL] Live verified decisions (UTC)")

        observed: list[JournalRow] = []
        seen_decisions: set[str] = set()
        seen_requests: set[str] = set()
        expected_call = 0

        def _expect_next_row() -> JournalRow:
            assert journal is not None
            idx = len(observed)
            if idx >= len(EXPECTED_SEQUENCE):
                raise DemoError("Unexpected extra gateway journal event.")
            row = journal.next_row(timeout=20.0)
            shape = (row.kind, row.route, row.tool, row.rule, row.result, row.reason)
            if shape != EXPECTED_SEQUENCE[idx]:
                raise DemoError("Gateway journal event did not match expected sequence.")
            if idx == 3:
                if (
                    row.decision_id != observed[2].decision_id
                    or row.request_id != observed[2].request_id
                ):
                    raise DemoError("Execution journal row did not pair with allowed decision.")
            else:
                if row.decision_id in seen_decisions or row.request_id in seen_requests:
                    raise DemoError("Duplicate decision_id or request_id in gateway journal.")
                seen_decisions.add(row.decision_id)
                seen_requests.add(row.request_id)
            observed.append(row)
            return row

        def on_prompt(text: str) -> None:
            if text not in (FIRST_PROMPT, RETRY_PROMPT):
                raise DemoError("Unexpected prompt text.")
            display.left(f"$ {text}")

        def on_result(index: int, receipt: Any) -> None:
            nonlocal expected_call
            if index != expected_call:
                raise DemoError("Tool result received out of expected order.")
            expected_call += 1
            row = _expect_next_row()
            constraint = _constraint_label(receipt)
            if receipt.reason == "ok":
                if receipt.message != "simulated" or (
                    receipt.decision_id is not None
                    and receipt.decision_id != row.decision_id
                ):
                    raise DemoError("Allowed refund receipt failed validation.")
                _expect_next_row()
                if not native_tui:
                    display.left(f"  allowed: {receipt.message}")
                display.right(
                    f"{row.utc_time}  {row.decision_id}  {row.tool}  {row.reason}  {constraint}"
                )
                return
            if receipt.decision_id != row.decision_id or receipt.reason != row.reason:
                raise DemoError("Tool denial receipt does not match gateway journal decision.")
            if not native_tui:
                display.left(f"  denied: {receipt.message} decision_id={receipt.decision_id}")
            display.right(
                f"{row.utc_time}  {row.decision_id}  {row.tool}  {row.reason}  {constraint}"
            )

        def revoke() -> None:
            if expected_call != 3:
                raise DemoError("Revoke invoked before completing initial three tool calls.")
            _revoke_control(control_sock)
            row = _expect_next_row()
            if not native_tui:
                display.left(f"$ revoke-chain -> confirmed decision_id={row.decision_id}")
            display.right(f"{row.utc_time}  {row.decision_id}  revoke  {row.reason}  chain revoked")

        if args.verify_relay:
            try:
                with McpStdioClient(
                    stoactl_bin, child_sock, private_root / "agent-home", "relay"
                ) as client:

                    def _call_relay(idx: int) -> None:
                        rpc = client.tools_call("refunds_create", CALL_ARGUMENTS[idx])
                        if (
                            not isinstance(rpc, dict)
                            or "error" in rpc
                            or not isinstance(rpc.get("result"), dict)
                        ):
                            raise DemoError("Relay tools/call returned invalid or error envelope.")
                        on_result(idx, parse_tool_result(idx, rpc["result"]))

                    client.initialize()
                    if "refunds_create" not in client.tools_list():
                        raise DemoError("Relay tools/list did not expose refunds_create.")
                    on_prompt(FIRST_PROMPT)
                    for idx in range(3):
                        _call_relay(idx)
                    revoke()
                    on_prompt(RETRY_PROMPT)
                    _call_relay(3)
            except DemoError:
                raise
            except Exception as exc:
                raise DemoError("Relay plumbing verification failed.") from exc
        else:
            assert claude_bin is not None and api_key_path is not None
            try:
                if native_tui:
                    assert session_id is not None
                    run_tui(
                        profile=claude_profile,
                        session_id=session_id,
                        tmux=display.tmux,
                        deadline=time.monotonic() + 180.0,
                        on_result=on_result,
                        revoke=revoke,
                    )
                else:
                    run_claude(
                        executable=claude_bin,
                        profile=claude_profile,
                        cwd=claude_cwd,
                        mcp_config=mcp_cfg,
                        api_key_file=api_key_path,
                        deadline=time.monotonic() + 180.0,
                        on_prompt=on_prompt,
                        on_result=on_result,
                        revoke=revoke,
                    )
            except DemoClientError as exc:
                raise DemoError(
                    "Claude Code scenario did not complete all verified steps."
                ) from exc

        if expected_call != 4 or len(observed) != len(EXPECTED_SEQUENCE):
            raise DemoError(
                "Scenario did not complete all four tool calls and expected journal sequence."
            )
        _verify_export(private_root, cenv, observed)
        auth_headers_seen = _verify_upstream_stats(cenv)
        elapsed = time.monotonic() - t0

        mode = (
            "verify-relay"
            if args.verify_relay
            else ("claude-code-tui" if native_tui else "claude-code")
        )
        summary_out = display.right if native_tui else display.left
        summary_out("")
        summary_out(f"PROOF ({mode}): 5 verified decisions/revocations + 1 paired execution")
        summary_out(f"ELAPSED: {elapsed:.2f}s (startup + scenario; excludes hold and teardown)")
        summary_out(f"UPSTREAM: caller_auth_headers_seen={auth_headers_seen}")
        display.hold(4.0)
    finally:

        def _compose_down() -> bool:
            if not compose_attempted:
                return True
            res = subprocess.run(
                ["docker", "compose", "down", "-v", "--remove-orphans"],
                cwd=ROOT,
                env=cenv,
                capture_output=True,
                timeout=45,
                check=False,
            )
            return res.returncode == 0

        def _rm_root() -> bool:
            if private_root.exists():
                shutil.rmtree(private_root)
            return True

        for step in (
            display.close,
            (journal.close if journal is not None else lambda: True),
            lambda: _kill_pg(relay_proc),
            _compose_down,
            _rm_root,
        ):
            try:
                if not step():
                    teardown_failed = True
            except (OSError, subprocess.TimeoutExpired):
                teardown_failed = True
        if teardown_failed and sys.exc_info()[0] is None:
            raise DemoError("One or more isolated demo resources failed to stop cleanly.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("error: demo interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("error: unexpected demo failure.", file=sys.stderr)
        raise SystemExit(1)
