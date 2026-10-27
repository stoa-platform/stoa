#!/usr/bin/env python3
"""Real Keycloak CLI/server credential-input check; never a Compose success claim."""
import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--distribution", type=Path, required=True, help="Checksum-verified Keycloak 26.5.3 distribution")
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    dist = args.distribution.resolve()
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        parser.error("JAVA_HOME must identify the supported Java 21 runtime")
    password = secrets.token_urlsafe(36)
    wrong = secrets.token_urlsafe(36)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        "PATH": os.environ["PATH"],
        "LANG": "en_US.UTF-8",
        "JAVA_HOME": java_home,
        "JAVA_OPTS": "-Xms128m -Xmx512m",
        "KC_BOOTSTRAP_ADMIN_USERNAME": "fixture",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": password,
    }
    server_args = [
        str(dist / "bin/kc.sh"), "start-dev", "--db=dev-mem",
        "--http-host=127.0.0.1", f"--http-port={port}", "--cache=local",
        "--hostname-strict=false", "--log-level=warn",
    ]
    server_log = []
    process = subprocess.Popen(
        server_args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )

    def drain():
        for line in process.stdout:
            server_log.append(line.replace(password, "[fixture]"))

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    results = {
        "server_version": "26.5.3", "real_server": True, "real_kcadm": True,
        "db": "dev-mem", "docker_used": False, "full_verify_compose_executed": False,
        "secrets_saved": False,
        "qualification_scope": "credential input via common authentication path, get realms --no-config; persistent config credentials initialization and complete Compose assertions are separate",
        "cases": [],
    }

    try:
        ready = False
        for _ in range(180):
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/realms/master/.well-known/openid-configuration",
                    timeout=1,
                ) as response:
                    ready = response.status == 200
            except Exception:
                pass
            if ready:
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("real Keycloak fixture did not become ready")
        text = (args.repo / "quickstart/verify.sh").read_text()
        block = text.split('echo "configuring keycloak realm"\n', 1)[1].split(
            '\nif ! docker compose exec', 1
        )[0].strip()
        # Docker is unavailable. Only replace its execution prefix and the command
        # storage mode. Keep the actual password pipe/export and shell logic intact.
        block = block.replace("docker compose exec -T keycloak ", "")
        block = block.replace("/opt/keycloak", str(dist))
        block = block.replace("config credentials", "get realms --no-config")
        block = block.replace("http://127.0.0.1:8080", f"http://127.0.0.1:{port}")
        assert "docker " not in block
        assert "get realms --no-config" in block
        for name, candidate, supplied in [
            ("valid", password, True), ("wrong", wrong, True),
            ("missing", "", False),
        ]:
            child_env = dict(env, kc_user="fixture", kc_pass=candidate)
            if supplied:
                child_env["KC_BOOTSTRAP_ADMIN_PASSWORD"] = candidate
            else:
                child_env.pop("KC_BOOTSTRAP_ADMIN_PASSWORD", None)
            child = subprocess.Popen(
                ["/bin/sh", "-eu", "-c", block], env=child_env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            sampled = 0
            credential_in_arguments = False
            deadline = time.monotonic() + 30
            while child.poll() is None:
                if time.monotonic() > deadline:
                    child.kill()
                    raise RuntimeError("CLI credential-input deadline")
                pending = [child.pid]
                pids = []
                while pending:
                    pid = pending.pop()
                    pids.append(pid)
                    r = subprocess.run(
                        ["pgrep", "-P", str(pid)], capture_output=True, text=True,
                    )
                    pending.extend(int(x) for x in r.stdout.split() if x.isdigit())
                r = subprocess.run(
                    ["ps", "-ww", "-o", "command=", "-p", ",".join(map(str, pids))],
                    capture_output=True, text=True,
                )
                sampled += 1
                credential_in_arguments |= any(s in r.stdout for s in [password, wrong])
                time.sleep(0.02)
            stdout, stderr = child.communicate(timeout=2)
            console = b"Console is not active" in stderr
            denied = b"invalid_grant" in stderr or b"Invalid user credentials" in stderr
            if name == "valid":
                passed = child.returncode == 0 and not console
            elif name == "wrong":
                passed = child.returncode != 0 and not console and denied
            else:
                passed = child.returncode != 0 and b"missing bootstrap credential" in stderr
            results["cases"].append({
                "case": name, "exit": child.returncode,
                "console_prompt_error": console, "passed": passed,
                "credential_rejected_by_keycloak": denied,
                "argument_samples": sampled,
                "credential_in_process_arguments": credential_in_arguments,
                "fixture_value_in_cli_output": any(
                    x.encode() in stdout + stderr for x in [password, wrong]
                ),
            })
            assert not credential_in_arguments
            assert not any(x.encode() in stdout + stderr for x in [password, wrong])
        results["pass"] = sum(x["passed"] for x in results["cases"])
        results["fail"] = len(results["cases"]) - results["pass"]
        results["script_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        thread.join(timeout=2)
        # Do not persist HTTP bodies, credentials, sessions, or arbitrary server logs.
        results["fixture_stopped"] = process.poll() is not None
        results["server_exit"] = process.returncode
        (args.out / "resultats.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))
    return int(bool(results.get("fail", 1)))


if __name__ == "__main__":
    raise SystemExit(main())
