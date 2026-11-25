"""Pre-deployment check of BACKEND_ENCRYPTION_KEY in the Kubernetes Secret.

Runs the script against a fake kubectl on PATH (no cluster): present, absent,
empty, Secret not found, kubectl failure, and the value never reaching stdout
or stderr.
"""

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_backend_encryption_key.py"
MARKER = "synthetic-key-marker-7f3a9c"  # stands in for a real value; must never be printed


def _fake_kubectl(tmp_path: Path, *, stdout: str = "", stderr: str = "", code: int = 0) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "out.txt").write_text(stdout)
    (tmp_path / "err.txt").write_text(stderr)
    exe = bin_dir / "kubectl"
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, pathlib\n"
        f"base = pathlib.Path({str(tmp_path)!r})\n"
        "(base / 'args.txt').write_text(' '.join(sys.argv[1:]))\n"
        "sys.stdout.write((base / 'out.txt').read_text())\n"
        "sys.stderr.write((base / 'err.txt').read_text())\n"
        f"sys.exit({code})\n"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def _secret(**data: str) -> str:
    return json.dumps({"kind": "Secret", "metadata": {"name": "stoa-control-plane-api-secrets"}, "data": data})


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)  # noqa: S603


def _assert_no_value(result: subprocess.CompletedProcess) -> None:
    for text in (result.stdout, result.stderr):
        assert MARKER not in text
        assert _b64(MARKER) not in text


def test_key_present(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER), OTHER=_b64("x")))
    result = _run(env)
    assert result.returncode == 0
    assert result.stdout.strip() == "BACKEND_ENCRYPTION_KEY in stoa-system/stoa-control-plane-api-secrets: present"
    _assert_no_value(result)
    args = (tmp_path / "args.txt").read_text()
    assert args == "get secret stoa-control-plane-api-secrets --namespace stoa-system --output json"


def test_key_absent(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=_secret(OTHER=_b64(MARKER)))
    result = _run(env)
    assert result.returncode == 1
    assert "absent" in result.stderr
    _assert_no_value(result)


@pytest.mark.parametrize("encoded", ["", _b64(""), _b64("   \n"), "not*base64"])
def test_key_empty(tmp_path, encoded):
    env = _fake_kubectl(tmp_path, stdout=_secret(BACKEND_ENCRYPTION_KEY=encoded))
    result = _run(env)
    assert result.returncode == 2
    assert "empty" in result.stderr


def test_secret_without_data(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=json.dumps({"kind": "Secret"}))
    assert _run(env).returncode == 1


def test_secret_not_found(tmp_path):
    env = _fake_kubectl(
        tmp_path,
        stderr='Error from server (NotFound): secrets "stoa-control-plane-api-secrets" not found\n',
        code=1,
    )
    result = _run(env)
    assert result.returncode == 3
    assert "secret not found" in result.stderr


def test_kubectl_error_is_not_echoed(tmp_path):
    env = _fake_kubectl(tmp_path, stderr=f"error: forbidden {MARKER}\n", code=1)
    result = _run(env)
    assert result.returncode == 4
    assert "kubectl failed" in result.stderr
    _assert_no_value(result)


def test_unparsable_output(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=f"not json {MARKER}")
    result = _run(env)
    assert result.returncode == 4
    _assert_no_value(result)


def test_kubectl_missing(tmp_path):
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert result.returncode == 4


def test_options_are_passed_to_kubectl(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=_secret(CUSTOM=_b64(MARKER)))
    result = _run(env, "--namespace", "cp", "--secret", "s", "--key", "CUSTOM", "--context", "staging")
    assert result.returncode == 0
    assert (tmp_path / "args.txt").read_text() == "get secret s --namespace cp --output json --context staging"
    _assert_no_value(result)


def test_value_never_printed_in_any_outcome(tmp_path):
    cases = [
        _secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)),
        _secret(OTHER=_b64(MARKER)),
        _secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER), EXTRA=MARKER),
    ]
    for i, stdout in enumerate(cases):
        case_dir = tmp_path / str(i)
        case_dir.mkdir()
        _assert_no_value(_run(_fake_kubectl(case_dir, stdout=stdout)))


def test_script_writes_no_files(tmp_path):
    env = _fake_kubectl(tmp_path, stdout=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)))
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run([sys.executable, str(SCRIPT)], env=env, cwd=work, capture_output=True, timeout=30, check=True)  # noqa: S603
    assert list(work.iterdir()) == []
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.name != "out.txt":
            assert MARKER not in path.read_text(errors="ignore")
            assert _b64(MARKER) not in path.read_text(errors="ignore")
