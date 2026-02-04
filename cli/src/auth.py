"""OIDC Authorization Code flow with PKCE for CLI login."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser

import httpx

from .config import Credentials, StoaConfig, save_credentials


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth2 callback."""

    authorization_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.authorization_code = params["code"][0]
            self._respond(
                200,
                "<html><body><h2>Login successful!</h2>"
                "<p>You can close this tab and return to the terminal.</p>"
                "</body></html>",
            )
        elif "error" in params:
            _CallbackHandler.error = params.get(
                "error_description", params["error"]
            )[0]
            self._respond(
                400,
                f"<html><body><h2>Login failed</h2>"
                f"<p>{_CallbackHandler.error}</p></body></html>",
            )
        else:
            self._respond(400, "<html><body><h2>Unexpected response</h2></body></html>")

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: object) -> None:
        pass  # silence server logs


def login_interactive(config: StoaConfig, port: int = 0) -> Credentials:
    """Run the full OIDC Authorization Code + PKCE flow.

    Opens a browser for the user to authenticate with Keycloak,
    captures the callback on a local server, exchanges the code
    for tokens, and returns Credentials.
    """
    code_verifier, code_challenge = _generate_pkce()

    # Start local callback server
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    actual_port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{actual_port}/callback"

    # Reset handler state
    _CallbackHandler.authorization_code = None
    _CallbackHandler.error = None

    # Build authorize URL
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(32),
    }
    authorize_url = f"{config.authorize_endpoint}?{urllib.parse.urlencode(params)}"

    # Open browser in background
    webbrowser.open(authorize_url)

    # Wait for callback (timeout 120s)
    server.timeout = 120
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=120)
    server.server_close()

    if _CallbackHandler.error:
        raise RuntimeError(f"Authentication failed: {_CallbackHandler.error}")
    if not _CallbackHandler.authorization_code:
        raise RuntimeError("Authentication timed out — no callback received.")

    # Exchange code for tokens
    return _exchange_code(
        config=config,
        code=_CallbackHandler.authorization_code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )


def _exchange_code(
    config: StoaConfig,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> Credentials:
    """Exchange authorization code for access + refresh tokens."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            config.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": config.client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    now = time.time()

    claims = _decode_jwt_claims(data["access_token"])

    creds = Credentials(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_at=now + data.get("expires_in", 300),
        token_type=data.get("token_type", "Bearer"),
        claims=claims,
    )
    save_credentials(creds)
    return creds


def refresh_token(config: StoaConfig, creds: Credentials) -> Credentials:
    """Use the refresh_token to obtain a new access_token."""
    if not creds.refresh_token:
        raise RuntimeError("No refresh token available. Run 'stoa login' again.")

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            config.token_endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": config.client_id,
                "refresh_token": creds.refresh_token,
            },
        )
    if resp.status_code >= 400:
        raise RuntimeError("Token refresh failed. Run 'stoa login' again.")

    data = resp.json()
    now = time.time()
    claims = _decode_jwt_claims(data["access_token"])

    new_creds = Credentials(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", creds.refresh_token),
        expires_at=now + data.get("expires_in", 300),
        token_type=data.get("token_type", "Bearer"),
        claims=claims,
    )
    save_credentials(new_creds)
    return new_creds


def _decode_jwt_claims(token: str) -> dict[str, object]:
    """Decode JWT payload without signature verification (for display only)."""
    try:
        payload = token.split(".")[1]
        # Add padding
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}
