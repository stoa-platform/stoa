"""Bounded HTTPS Admin REST adapter with default CA validation."""

import http.client
import json
import re
import ssl
from urllib.parse import urlsplit

from keycloak_migration.core import MAX_BYTES, MigrationError, exact_uri, identifier, require


class Admin:
    """HTTPS only, CA validation, no redirect/proxy/retry, bounded response and timeout."""

    def __init__(self, url, realm, token):
        exact_uri(url)
        require(
            isinstance(token, str) and bool(re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,16384}", token)),
            "Invalid bearer input; details withheld",
        )
        parsed = urlsplit(url)
        self.host, self.port = parsed.hostname, parsed.port
        self.prefix = parsed.path.rstrip("/")
        self.root = "/admin/realms/" + identifier(realm)
        self.realm = realm
        self.origin = url.rstrip("/")
        self.token = token
        # create_default_context() honors SSLKEYLOGFILE and may log TLS secrets.
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.load_default_certs()

    def request(self, method, path, data=None):
        conn = None
        try:
            conn = http.client.HTTPSConnection(
                self.host, self.port, timeout=20, context=self.context
            )
            body = None if data is None else json.dumps(data).encode()
            conn.request(
                method,
                self.prefix + self.root + path,
                body=body,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response = conn.getresponse()
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "API response exceeded the size limit")
            require(
                response.status in ({200} if method == "GET" else {200, 201, 204}),
                "Admin API rejected the request; stop and replan (response withheld)",
            )
            return json.loads(raw) if raw else None
        except MigrationError:
            raise
        except (OSError, ValueError, http.client.HTTPException):
            raise MigrationError(
                "Admin API transport/JSON failure; stop and replan (details withheld)"
            ) from None
        finally:
            if conn:
                conn.close()

    def get(self, path):
        return self.request("GET", path)

    def clients(self):
        result = []
        for first in range(0, 100000, 100):
            page = self.get(f"/clients?first={first}&max=100")
            require(isinstance(page, list) and len(page) <= 100)
            result.extend(page)
            if len(page) < 100:
                return result
        raise MigrationError("Client inventory limit reached; nothing applied")

    def binding(self):
        return {"url": self.origin, "realm": self.realm}
