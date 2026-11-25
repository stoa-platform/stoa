"""Pre-deployment check of BACKEND_ENCRYPTION_KEY in the Kubernetes Secret.

Runs the script against a fake kubectl on PATH (no cluster). The fake renders
the script's go-template the way kubectl does (only the requested field, or
nothing when the field is absent). Covers present, absent, empty, public
development key, Secret not found, kubectl failure, and the value never
reaching stdout or stderr.
"""

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import src.services.encryption_service as enc_mod

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_backend_encryption_key.py"
MARKER = "synthetic-key-marker-7f3a9c"  # stands in for a real value; must never be printed
NAME = "stoa-control-plane-api-secrets"

FAKE_KUBECTL = """#!/usr/bin/env python3
import json, pathlib, re, sys
base = pathlib.Path(BASE)
argv = sys.argv[1:]
(base / "args.json").write_text(json.dumps(argv))
config = json.loads((base / "config.json").read_text())
sys.stderr.write(config["stderr"])
if config["code"]:
    sys.exit(config["code"])
if config["raw"] is not None:
    sys.stdout.write(config["raw"])
    sys.exit(0)
outputs = [a for a in argv if a.startswith("--output=go-template=")]
assert len(outputs) == 1, argv
template = outputs[0].split("=", 2)[2]
match = re.fullmatch(r'[{][{]range [$]k, [$]v := [.]data[}][}][{][{]if eq [$]k "([^"]+)"[}][}]=[{][{][$]v[}][}][{][{]end[}][}][{][{]end[}][}]', template)
assert match, template
data = (config["document"] or {}).get("data") or {}
if match.group(1) in data:
    sys.stdout.write("=" + data[match.group(1)])
"""


def _fake_kubectl(
    tmp_path: Path, *, document: dict | None = None, raw: str | None = None, stderr: str = "", code: int = 0
) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    config = {"document": document, "raw": raw, "stderr": stderr, "code": code}
    (tmp_path / "config.json").write_text(json.dumps(config))
    exe = bin_dir / "kubectl"
    exe.write_text(FAKE_KUBECTL.replace("BASE", repr(str(tmp_path)), 1))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def _secret(**data: str) -> dict:
    return {"kind": "Secret", "metadata": {"name": NAME}, "data": data}


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)  # noqa: S603


def _argv(tmp_path: Path) -> list[str]:
    return json.loads((tmp_path / "args.json").read_text())


def _assert_no_value(result: subprocess.CompletedProcess) -> None:
    dev = enc_mod._DEV_FERNET_KEY.decode()
    for text in (result.stdout, result.stderr):
        assert MARKER not in text
        assert _b64(MARKER) not in text
        assert dev not in text
        assert _b64(dev) not in text


def _template_for(field: str) -> str:
    return (
        f'--output=go-template={{{{range $k, $v := .data}}}}{{{{if eq $k "{field}"}}}}={{{{$v}}}}{{{{end}}}}{{{{end}}}}'
    )


def test_key_present(tmp_path):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER), OTHER=_b64("x")))
    result = _run(env)
    assert result.returncode == 0
    assert result.stdout.strip() == f"BACKEND_ENCRYPTION_KEY in stoa-system/{NAME}: present"
    _assert_no_value(result)
    assert _argv(tmp_path) == [
        "get",
        "secret",
        NAME,
        "--namespace",
        "stoa-system",
        _template_for("BACKEND_ENCRYPTION_KEY"),
    ]


def test_only_target_field_requested(tmp_path):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)))
    _run(env)
    argv = _argv(tmp_path)
    assert not any(a in ("json", "yaml", "-o", "--output") or a.startswith(("-ojson", "--output=json")) for a in argv)
    assert sum(a.startswith("--output=go-template=") for a in argv) == 1


def test_key_absent(tmp_path):
    env = _fake_kubectl(tmp_path, document=_secret(OTHER=_b64(MARKER)))
    result = _run(env)
    assert result.returncode == 1
    assert "absent" in result.stderr
    _assert_no_value(result)


@pytest.mark.parametrize("encoded", ["", _b64(""), _b64("   \n"), "not*base64"])
def test_key_empty(tmp_path, encoded):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=encoded))
    result = _run(env)
    assert result.returncode == 2
    assert "empty" in result.stderr


@pytest.mark.parametrize("padding", ["", "\n", "  "])
def test_public_dev_key_reported_as_dev_key(tmp_path, padding):
    dev = enc_mod._DEV_FERNET_KEY.decode() + padding
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(dev)))
    result = _run(env)
    assert result.returncode == 5
    assert result.stderr.strip() == (
        f"BACKEND_ENCRYPTION_KEY in stoa-system/{NAME}: public development key (treated as absent)"
    )
    assert result.stdout == ""
    _assert_no_value(result)


def _reencoded_dev_keys() -> list[str]:
    decoded = base64.urlsafe_b64decode(enc_mod._DEV_FERNET_KEY)
    return [base64.urlsafe_b64encode(decoded).decode(), base64.b64encode(decoded).decode()]


@pytest.mark.parametrize("encoded", _reencoded_dev_keys())
def test_dev_key_compared_on_decoded_bytes(tmp_path, encoded):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(encoded)))
    result = _run(env)
    assert result.returncode == 5
    assert result.stdout == ""
    _assert_no_value(result)
    assert encoded not in result.stderr


@pytest.mark.parametrize("value", [MARKER, "!!!!", "c2hvcnQ"])
def test_other_values_are_present(tmp_path, value):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(value)))
    assert _run(env).returncode == 0


def test_dev_key_digest_matches_service_constant():
    import hashlib
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_backend_encryption_key", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decoded = base64.urlsafe_b64decode(enc_mod._DEV_FERNET_KEY)
    assert hashlib.sha256(decoded).digest() == module.PUBLISHED_DEFAULT_SHA256
    assert enc_mod._DEV_FERNET_KEY.decode() not in SCRIPT.read_text()


def test_secret_without_data(tmp_path):
    env = _fake_kubectl(tmp_path, document={"kind": "Secret"})
    assert _run(env).returncode == 1


def test_secret_not_found(tmp_path):
    env = _fake_kubectl(
        tmp_path,
        stderr=f'Error from server (NotFound): secrets "{NAME}" not found\n',
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


def test_unexpected_output(tmp_path):
    env = _fake_kubectl(tmp_path, raw=f"unexpected {MARKER}")
    result = _run(env)
    assert result.returncode == 4
    _assert_no_value(result)


def test_kubectl_missing(tmp_path):
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert result.returncode == 4


@pytest.mark.parametrize("field", ['X"}}{{.}}{{"', "A B", "", "x/y"])
def test_invalid_key_name_rejected_before_kubectl(tmp_path, field):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)))
    result = _run(env, "--key", field)
    assert result.returncode == 4
    assert "invalid key name" in result.stderr
    assert not (tmp_path / "args.json").exists()
    _assert_no_value(result)


def test_options_are_passed_to_kubectl(tmp_path):
    env = _fake_kubectl(tmp_path, document=_secret(CUSTOM=_b64(MARKER)))
    result = _run(env, "--namespace", "cp", "--secret", "s", "--key", "CUSTOM", "--context", "staging")
    assert result.returncode == 0
    assert _argv(tmp_path) == [
        "get",
        "secret",
        "s",
        "--namespace",
        "cp",
        _template_for("CUSTOM"),
        "--context",
        "staging",
    ]
    _assert_no_value(result)


def test_value_never_printed_in_any_outcome(tmp_path):
    dev = enc_mod._DEV_FERNET_KEY.decode()
    cases = [
        _secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)),
        _secret(OTHER=_b64(MARKER)),
        _secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER), EXTRA=MARKER),
        _secret(BACKEND_ENCRYPTION_KEY=_b64(dev)),
        _secret(BACKEND_ENCRYPTION_KEY=MARKER),
    ]
    for i, document in enumerate(cases):
        case_dir = tmp_path / str(i)
        case_dir.mkdir()
        _assert_no_value(_run(_fake_kubectl(case_dir, document=document)))


def test_script_writes_no_files(tmp_path):
    env = _fake_kubectl(tmp_path, document=_secret(BACKEND_ENCRYPTION_KEY=_b64(MARKER)))
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run([sys.executable, str(SCRIPT)], env=env, cwd=work, capture_output=True, timeout=30, check=True)  # noqa: S603
    assert list(work.iterdir()) == []
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.name != "config.json":
            assert MARKER not in path.read_text(errors="ignore")
            assert _b64(MARKER) not in path.read_text(errors="ignore")
