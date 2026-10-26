"""Run the SDK smoke with a loopback OIDC peer and an ephemeral signing key."""

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from mcp_sdk_smoke import _format, run_smoke


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def main():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "smoke",
                "alg": "RS256",
                "use": "sig",
                "n": encoded(public.n.to_bytes(256, "big")),
                "e": "AQAB",
            }
        ]
    }

    class Peer(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/realms/stoa/.well-known/openid-configuration":
                body = {
                    "issuer": issuer,
                    "authorization_endpoint": issuer + "/auth",
                    "token_endpoint": issuer + "/token",
                    "jwks_uri": issuer + "/jwks",
                }
            elif self.path == "/realms/stoa/jwks":
                body = jwks
            else:
                self.send_error(404)
                return
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Peer) as peer:
        base = f"http://127.0.0.1:{peer.server_port}"
        issuer = base + "/realms/stoa"
        threading.Thread(target=peer.serve_forever, daemon=True).start()
        now = int(time.time())
        header = encoded(json.dumps({"alg": "RS256", "kid": "smoke"}).encode())
        claims = encoded(
            json.dumps(
                {
                    "iss": issuer,
                    "aud": "mcp-smoke",
                    "sub": "smoke-user",
                    "tenant_id": "smoke-tenant",
                    "iat": now,
                    "exp": now + 300,
                    "scope": "stoa:read",
                }
            ).encode()
        )
        signed = f"{header}.{claims}".encode()
        token = (
            signed.decode() + "." + encoded(key.sign(signed, padding.PKCS1v15(), hashes.SHA256()))
        )
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "STOA_HOST": "127.0.0.1",
            "STOA_PORT": str(port),
            "STOA_KEYCLOAK_URL": base,
            "STOA_KEYCLOAK_REALM": "stoa",
            "STOA_KEYCLOAK_CLIENT_ID": "mcp-smoke",
            "STOA_MCP_AUDIENCE": "mcp-smoke",
            "STOA_CONTROL_PLANE_URL": base,
            "STOA_OTEL_ENDPOINT": "",
        }
        binary = Path(sys.argv[1] if len(sys.argv) > 1 else "target/release/stoa-gateway").resolve()
        try:
            with tempfile.TemporaryFile() as log:
                with subprocess.Popen([str(binary)], env=env, stdout=log, stderr=log) as gateway:
                    try:
                        for _ in range(100):
                            if gateway.poll() is not None:
                                raise RuntimeError("local gateway exited before readiness")
                            try:
                                with urllib.request.urlopen(url + "/health", timeout=1):
                                    break
                            except (urllib.error.URLError, TimeoutError):
                                time.sleep(0.1)
                        else:
                            raise RuntimeError("local gateway readiness timed out")
                        rejected = asyncio.run(run_smoke(url + "/mcp/sse", "dummy", False))
                        assert any(not result.ok for result in rejected), "unsigned bearer accepted"
                        print("Unsigned bearer rejected")
                        results = asyncio.run(run_smoke(url + "/mcp/sse", token, False))
                        ok, body = _format(results)
                        print(body)
                        assert ok, "authenticated MCP SDK smoke failed"
                        assert any(
                            result.name == "tools/list" for result in results
                        ), "discovery must run"
                        print(f"Authenticated MCP SDK smoke PASS ({len(results)} stages)")
                    finally:
                        gateway.terminate()
                        try:
                            gateway.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            gateway.kill()
                            gateway.wait()
        finally:
            peer.shutdown()


if __name__ == "__main__":
    main()
