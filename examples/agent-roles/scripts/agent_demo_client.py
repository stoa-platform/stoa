from __future__ import annotations

import json
import os
import re
import select
import signal
import stat
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CALL_ARGUMENTS: tuple[dict[str, Any], ...] = (
    {"customer_id": "C-1042", "amount_eur": 80, "currency": "EUR"},
    {"customer_id": "C-2000", "amount_eur": 50, "currency": "EUR"},
    {"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR"},
    {"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR"},
)

FIRST_PROMPT = (
    "Refund customer C-1042 \u20ac80, then refund customer C-2000 \u20ac50, "
    "then refund C-1042 \u20ac50."
)
RETRY_PROMPT = "Refund customer C-1042 \u20ac50."
STORY_ALLOW_PROMPT = (
    "Refund customer C-1042 EUR 50. Call refunds_create exactly once and report the result."
)
STORY_DENY_PROMPT = (
    "Refund customer C-1042 EUR 80. Call refunds_create exactly once and report the result."
)

_TOOL_NAME = "mcp__refunds__refunds_create"
_SYSTEM_PROMPT = (
    "Use only mcp__refunds__refunds_create. Make one separate tool call at a time "
    "in the exact requested order. Continue after a denial and never retry unless "
    "prompted."
)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_API_KEY_BYTES = 4096
_MAX_LINE_BYTES = 65536

_ERROR_SIGNATURES: dict[int, tuple[str, tuple[tuple[str, str | None], ...]]] = {
    0: (
        "Tool call rejected by role policy",
        (
            ("decision_id", None),
            ("reason", "argument_constraint_denied"),
            ("constraint", "amount_exceeds_cap"),
            ("limit_eur", "50"),
        ),
    ),
    1: (
        "Tool call rejected by role policy",
        (
            ("decision_id", None),
            ("reason", "argument_constraint_denied"),
            ("constraint", "customer_outside_scope"),
        ),
    ),
    3: (
        "Chain revoked",
        (
            ("decision_id", None),
            ("reason", "chain_revoked"),
        ),
    ),
}


class DemoClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class Receipt:
    decision_id: str | None
    reason: str
    constraint: str | None
    limit_eur: int | None
    message: str


def _strict_object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise DemoClientError("duplicate json key")
        obj[key] = value
    return obj


def _reject_json_constant(_value: str) -> Any:
    raise DemoClientError("invalid json constant")


def _strict_loads(text: str, error_msg: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object_pairs_hook,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, RecursionError, DemoClientError):
        raise DemoClientError(error_msg) from None


def _exact_dict_match(actual: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(actual, dict) or set(actual.keys()) != set(expected.keys()):
        return False
    for key, exp_val in expected.items():
        act_val = actual[key]
        if type(act_val) is not type(exp_val) or act_val != exp_val:
            return False
    return True


def parse_tool_result(index: int, result: dict[str, Any]) -> Receipt:
    if type(index) is not int or index < 0 or index >= len(CALL_ARGUMENTS):
        raise DemoClientError("invalid tool result index")
    if not isinstance(result, dict) or set(result.keys()) != {"isError", "content"}:
        raise DemoClientError("invalid tool result envelope")

    is_error = result["isError"]
    content = result["content"]
    if type(is_error) is not bool or not isinstance(content, list):
        raise DemoClientError("invalid tool result envelope")

    if index == 2:
        if len(content) not in (1, 2):
            raise DemoClientError("invalid tool result envelope")
    elif len(content) != 1:
        raise DemoClientError("invalid tool result envelope")

    for block in content:
        if (
            not isinstance(block, dict)
            or set(block.keys()) != {"type", "text"}
            or block["type"] != "text"
            or type(block["text"]) is not str
        ):
            raise DemoClientError("invalid tool result content")

    text = content[0]["text"]

    if index == 2:
        if is_error is not False:
            raise DemoClientError("unexpected tool result status")
        parsed = _strict_loads(text, "invalid tool result payload")
        expected = {**CALL_ARGUMENTS[2], "status": "simulated"}
        if not _exact_dict_match(parsed, expected):
            raise DemoClientError("invalid tool result payload")
        decision_id: str | None = None
        if len(content) == 2:
            second_text = content[1]["text"]
            prefix = "decision_id="
            if not second_text.startswith(prefix):
                raise DemoClientError("invalid tool result payload")
            candidate = second_text[len(prefix) :]
            if not _UUID_RE.fullmatch(candidate):
                raise DemoClientError("invalid tool result payload")
            decision_id = candidate
        return Receipt(
            decision_id=decision_id,
            reason="ok",
            constraint=None,
            limit_eur=None,
            message=parsed["status"],
        )

    if is_error is not True:
        raise DemoClientError("unexpected tool result status")
    if "\r" in text:
        raise DemoClientError("invalid tool result payload")
    if text.endswith("\n"):
        text = text[:-1]
    lines = text.split("\n")

    expected_header, expected_fields = _ERROR_SIGNATURES[index]
    if len(lines) != 1 + len(expected_fields) or lines[0] != expected_header:
        raise DemoClientError("invalid tool result payload")

    fields: dict[str, str] = {}
    for line, (key, expected_val) in zip(lines[1:], expected_fields, strict=False):
        prefix = f"{key}="
        if not line.startswith(prefix):
            raise DemoClientError("invalid tool result payload")
        val = line[len(prefix) :]
        if expected_val is None:
            if not _UUID_RE.fullmatch(val):
                raise DemoClientError("invalid tool result payload")
        elif val != expected_val:
            raise DemoClientError("invalid tool result payload")
        fields[key] = val

    limit_eur = int(fields["limit_eur"]) if "limit_eur" in fields else None
    return Receipt(
        decision_id=fields["decision_id"],
        reason=fields["reason"],
        constraint=fields.get("constraint"),
        limit_eur=limit_eur,
        message=lines[0],
    )


def _read_api_key_file(path: Path) -> str:
    if not isinstance(path, Path):
        raise DemoClientError("invalid api key file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError:
        raise DemoClientError("invalid api key file") from None

    try:
        st = os.fstat(fd)
        if (
            not stat.S_ISREG(st.st_mode)
            or stat.S_IMODE(st.st_mode) != 0o600
            or st.st_uid != os.getuid()
            or st.st_size <= 0
            or st.st_size > _MAX_API_KEY_BYTES
        ):
            raise DemoClientError("invalid api key file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, _MAX_API_KEY_BYTES + 1 - total)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_API_KEY_BYTES:
                raise DemoClientError("invalid api key file")
            chunks.append(chunk)
    except DemoClientError:
        raise
    except OSError:
        raise DemoClientError("invalid api key file") from None
    finally:
        os.close(fd)

    try:
        raw = b"".join(chunks).decode("ascii")
    except UnicodeDecodeError:
        raise DemoClientError("invalid api key file") from None
    if raw.endswith("\n"):
        raw = raw[:-1]
    if not raw or not all(0x21 <= ord(ch) <= 0x7E for ch in raw):
        raise DemoClientError("invalid api key file")
    return raw


def validate_api_key_file(path: Path) -> None:
    _read_api_key_file(path)


def _check_deadline(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DemoClientError("demo deadline exceeded")
    return remaining


class _NdjsonReader:
    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buf = bytearray()
        self._eof = False

    def read_event(self, deadline: float) -> dict[str, Any] | None:
        while True:
            remaining = _check_deadline(deadline)
            nl = self._buf.find(b"\n")
            if nl != -1:
                if nl > _MAX_LINE_BYTES:
                    raise DemoClientError("stdout line too large")
                raw_line = bytes(self._buf[:nl]).rstrip(b"\r")
                del self._buf[: nl + 1]
                if not raw_line.strip():
                    continue
                return self._decode_event(raw_line)
            if len(self._buf) > _MAX_LINE_BYTES:
                raise DemoClientError("stdout line too large")
            if self._eof:
                if not self._buf:
                    return None
                raw_line = bytes(self._buf).rstrip(b"\r")
                self._buf.clear()
                return self._decode_event(raw_line) if raw_line.strip() else None
            ready, _, _ = select.select([self._fd], [], [], remaining)
            if not ready:
                raise DemoClientError("demo deadline exceeded")
            try:
                chunk = os.read(self._fd, 4096)
            except OSError:
                raise DemoClientError("stdout read failed") from None
            if not chunk:
                self._eof = True
            else:
                self._buf.extend(chunk)

    @staticmethod
    def _decode_event(raw_line: bytes) -> dict[str, Any]:
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            raise DemoClientError("invalid stream event") from None
        event = _strict_loads(text, "invalid stream event")
        if not isinstance(event, dict):
            raise DemoClientError("invalid stream event")
        return event


def _cleanup_process_group(proc: subprocess.Popen[bytes]) -> None:
    for stream in (proc.stdin, proc.stdout):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        pass
    if proc.poll() is None:
        try:
            proc.wait(timeout=0.3)
        except (subprocess.TimeoutExpired, OSError):
            pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=1.0)
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_claude(
    executable: str,
    profile: Path,
    cwd: Path,
    mcp_config: Path,
    api_key_file: Path | None,
    deadline: float,
    on_prompt: Callable[[str], None],
    on_result: Callable[[int, Receipt], None],
    revoke: Callable[[], None] | None = None,
    *,
    home_dir: Path | None = None,
    settings_file: Path | None = None,
    model: str | None = None,
    anthropic_base_url: str | None = None,
    anthropic_auth_token: str | None = None,
    turns: tuple[tuple[str, tuple[int, ...]], ...] | None = None,
) -> None:
    _check_deadline(deadline)
    env = {
        "PATH": os.defpath,
        "CLAUDE_CONFIG_DIR": str(profile),
        "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
        "DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if home_dir is not None:
        env["HOME"] = str(home_dir)
    if api_key_file is not None:
        if anthropic_base_url is not None or anthropic_auth_token is not None:
            raise DemoClientError("conflicting authentication configuration")
        env["ANTHROPIC_API_KEY"] = _read_api_key_file(api_key_file)
    else:
        if not anthropic_base_url or not anthropic_auth_token:
            raise DemoClientError("missing authentication configuration")
        env["ANTHROPIC_BASE_URL"] = anthropic_base_url
        env["ANTHROPIC_AUTH_TOKEN"] = anthropic_auth_token

    if turns is None:
        turn_specs: tuple[tuple[str, tuple[int, ...]], ...] = (
            (FIRST_PROMPT, (0, 1, 2)),
            (RETRY_PROMPT, (3,)),
        )
        revoke_after_first = True
    else:
        if not turns or any(
            not prompt or not idxs or any(not (0 <= i < len(CALL_ARGUMENTS)) for i in idxs)
            for prompt, idxs in turns
        ):
            raise DemoClientError("invalid scenario turns")
        turn_specs = turns
        revoke_after_first = False

    argv = [
        executable,
        "--bare",
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp_config),
        "--no-session-persistence",
        "--setting-sources",
        "",
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--allowedTools",
        _TOOL_NAME,
        "--system-prompt",
        _SYSTEM_PROMPT,
    ]
    if model is not None:
        argv.extend(["--model", model])
    if settings_file is not None:
        argv.extend(["--settings", str(settings_file)])
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        raise DemoClientError("failed to start claude process") from None

    turn_idx = 0
    step_in_turn = 0
    in_flight_id: str | None = None
    seen_call_ids: set[str] = set()
    seen_decision_ids: set[str] = set()
    done = False

    try:
        if proc.stdin is None or proc.stdout is None:
            raise DemoClientError("process stdio unavailable")
        reader = _NdjsonReader(proc.stdout.fileno())

        def send_prompt(prompt: str) -> None:
            _check_deadline(deadline)
            on_prompt(prompt)
            payload = (
                json.dumps(
                    {
                        "type": "user",
                        "message": {"role": "user", "content": prompt},
                        "parent_tool_use_id": None,
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            try:
                proc.stdin.write(payload)
                proc.stdin.flush()
            except OSError:
                raise DemoClientError("failed to write prompt") from None

        send_prompt(turn_specs[0][0])

        while True:
            event = reader.read_event(deadline)
            if event is None:
                if done:
                    break
                raise DemoClientError("unexpected end of stream")
            if event.get("parent_tool_use_id") is not None:
                raise DemoClientError("unexpected nested tool event")

            event_type = event.get("type")
            if event_type == "system":
                if event.get("subtype") == "permission_denied" or event.get("permission_denials"):
                    raise DemoClientError("permission denied")
                continue

            if event_type in ("assistant", "user"):
                msg = event.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype not in ("tool_use", "tool_result"):
                        continue
                    if done:
                        raise DemoClientError("unexpected trailing tool event")
                    expected_indices = turn_specs[turn_idx][1]
                    if event_type == "assistant" and btype == "tool_use":
                        if in_flight_id is not None:
                            raise DemoClientError("concurrent tool call")
                        if step_in_turn >= len(expected_indices):
                            raise DemoClientError("unexpected extra tool call")
                        call_idx = expected_indices[step_in_turn]
                        if block.get("name") != _TOOL_NAME:
                            raise DemoClientError("unexpected tool name")
                        tool_id = block.get("id")
                        if type(tool_id) is not str or not tool_id or tool_id in seen_call_ids:
                            raise DemoClientError("invalid tool call id")
                        if not _exact_dict_match(
                            block.get("input"), CALL_ARGUMENTS[call_idx]
                        ):
                            raise DemoClientError("unexpected tool arguments")
                        seen_call_ids.add(tool_id)
                        in_flight_id = tool_id
                    elif event_type == "user" and btype == "tool_result":
                        if in_flight_id is None or block.get("tool_use_id") != in_flight_id:
                            raise DemoClientError("mismatched tool result id")
                        call_idx = expected_indices[step_in_turn]
                        is_err = block.get("is_error", False)
                        raw_c = block.get("content")
                        norm_c = [{"type": "text", "text": raw_c}] if type(raw_c) is str else raw_c
                        if type(is_err) is not bool or not isinstance(norm_c, list):
                            raise DemoClientError("invalid tool result content")
                        receipt = parse_tool_result(
                            call_idx, {"isError": is_err, "content": norm_c}
                        )
                        if receipt.decision_id is not None:
                            if receipt.decision_id in seen_decision_ids:
                                raise DemoClientError("duplicate decision id")
                            seen_decision_ids.add(receipt.decision_id)
                        in_flight_id = None
                        step_in_turn += 1
                        on_result(call_idx, receipt)
                    else:
                        raise DemoClientError("role mismatched tool block")

            elif event_type == "result":
                if done:
                    raise DemoClientError("unexpected trailing result event")
                if event.get("permission_denials"):
                    raise DemoClientError("permission denied")
                if event.get("subtype") != "success" or event.get("is_error") is not False:
                    raise DemoClientError("unsuccessful turn result")
                expected_indices = turn_specs[turn_idx][1]
                if in_flight_id is not None or step_in_turn != len(expected_indices):
                    raise DemoClientError("incomplete tool call sequence")
                if turn_idx + 1 < len(turn_specs):
                    if revoke_after_first and turn_idx == 0 and revoke is not None:
                        _check_deadline(deadline)
                        revoke()
                    turn_idx += 1
                    step_in_turn = 0
                    send_prompt(turn_specs[turn_idx][0])
                else:
                    done = True
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass

        remaining = _check_deadline(deadline)
        try:
            returncode = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise DemoClientError("demo deadline exceeded") from None
        if returncode != 0:
            raise DemoClientError("claude process failed")
    finally:
        _cleanup_process_group(proc)
