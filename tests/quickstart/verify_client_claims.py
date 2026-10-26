#!/usr/bin/env python3
"""Check the actual quickstart client against a local, in-memory Keycloak.

This validates issued JWT claims, not the Docker gateway or HTTP access path.
The operator supplies an existing Keycloak 26.5.3 distribution and Java 21.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import jwt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    dist = args.distribution.resolve()
    source = (args.repo / "quickstart/verify.sh").read_text()
    block = source.split('client_secret="$(openssl rand -hex 24)"\n', 1)[1].split(
        "\n\ncontract=", 1
    )[0]
    prefix = "docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh create clients"
    assert block.count(prefix) == 1
    admin_password = secrets.token_urlsafe(36)
    client_secret = secrets.token_urlsafe(36)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    issuer = base + "/realms/quickstart"
    env = {
        "PATH": os.environ["PATH"], "LANG": "en_US.UTF-8",
        "HOME": str(args.out / "home"), "JAVA_HOME": str(args.java_home),
        "JAVA_OPTS": "-Xms128m -Xmx512m",
        "KC_BOOTSTRAP_ADMIN_USERNAME": "fixture",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
        "KC_CLI_PASSWORD": admin_password,
        "REALM": "quickstart", "CLIENT_ID": "quickstart-caller",
        "client_secret": client_secret,
    }
    process = subprocess.Popen(
        [str(dist / "bin/kc.sh"), "start-dev", "--db=dev-mem",
         "--http-host=127.0.0.1", f"--http-port={port}", "--cache=local",
         "--hostname-strict=false", "--log-level=warn"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    # Drain without saving arbitrary HTTP/server output or credentials.
    thread = threading.Thread(target=lambda: list(process.stdout), daemon=True)
    thread.start()
    result = {
        "real_keycloak": True, "real_kcadm": True, "db": "dev-mem",
        "docker_gateway_executed": False, "full_compose_executed": False,
        "secrets_saved": False, "cases": [],
        "verify_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }

    def request(path, payload=None, token=None, form=False):
        headers = {}
        data = None
        if payload is not None:
            data = (urllib.parse.urlencode(payload).encode() if form
                    else json.dumps(payload).encode())
            headers["Content-Type"] = ("application/x-www-form-urlencoded" if form
                                       else "application/json")
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read()
            return json.loads(body) if body else None

    try:
        for _ in range(180):
            if process.poll() is not None:
                raise RuntimeError("Keycloak fixture stopped before readiness")
            try:
                request("/realms/master/.well-known/openid-configuration")
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Keycloak fixture readiness deadline")
        admin = request("/realms/master/protocol/openid-connect/token", {
            "grant_type": "password", "client_id": "admin-cli",
            "username": "fixture", "password": admin_password,
        }, form=True)["access_token"]
        result["server_version"] = request("/admin/serverinfo", token=admin)["systemInfo"]["version"]
        assert result["server_version"] == "26.5.3"
        request("/admin/realms", {"realm": "quickstart", "enabled": True}, token=admin)
        cli = (str(dist / "bin/kcadm.sh") + " create clients --no-config --server "
               + base + " --realm master --user fixture")
        # Keep the client's actual stdin JSON, flags and mappers unchanged.
        command = block.replace(prefix, cli)
        assert "docker " not in command
        created = subprocess.run(["bash", "-euo", "pipefail", "-c", command],
                                 env=env, capture_output=True, timeout=40)
        assert not any(s.encode() in created.stdout + created.stderr
                       for s in (admin_password, client_secret))
        if created.returncode:
            raise RuntimeError("Native client configuration failed")
        response = request("/realms/quickstart/protocol/openid-connect/token", {
            "grant_type": "client_credentials", "client_id": "quickstart-caller",
            "client_secret": client_secret,
        }, form=True)
        token = response["access_token"]
        key = jwt.PyJWKClient(issuer + "/protocol/openid-connect/certs").get_signing_key_from_jwt(token)
        # Diagnostic fields only; they are not accepted as an authenticated identity.
        payload = token.split(".")[1]
        observed = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        result["issued_audience"] = observed.get("aud")
        result["issued_tenant"] = observed.get("tenant_id")
        options = {"require": ["exp", "iat", "sub", "iss", "aud", "tenant_id"]}
        for name, audience, expected_issuer, allowed in [
            ("configured_resource_and_tenant", "stoa-mcp-gateway", issuer, True),
            ("other_resource_rejected", "other-resource", issuer, False),
            ("other_issuer_rejected", "stoa-mcp-gateway", base + "/realms/other", False),
        ]:
            try:
                claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=audience,
                                    issuer=expected_issuer, options=options)
                passed = allowed and claims["tenant_id"] == "quickstart"
                error = None
            except jwt.InvalidTokenError as exc:
                passed = not allowed
                error = type(exc).__name__
            result["cases"].append({"case": name, "passed": passed, "error": error})
        result["pass"] = sum(c["passed"] for c in result["cases"])
        result["fail"] = len(result["cases"]) - result["pass"]
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        thread.join(timeout=2)
        result["fixture_stopped"] = process.poll() is not None
        result["server_exit"] = process.returncode
        (args.out / "resultats.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return int(bool(result.get("fail", 1)))


if __name__ == "__main__":
    raise SystemExit(main())
