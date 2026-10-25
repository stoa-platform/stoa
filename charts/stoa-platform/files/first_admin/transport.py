"""Bounded Keycloak admin transport for on-site bootstrap."""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


class Refused(Exception):
    """Value-free operational failure."""

    def __init__(self, reason: str, code: int = 23):
        super().__init__(reason)
        self.reason = reason
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Refused("redirect_refused")


class Keycloak:
    def __init__(self, url: str, realm: str, username: str, password: str):
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise Refused("invalid_endpoint", 22)
        self.url = url.rstrip("/")
        self.root = "/admin/realms/" + urllib.parse.quote(realm, safe="")
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        self.token = ""
        form = urllib.parse.urlencode(
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            }
        ).encode()
        result = self.request(
            "POST", "/realms/master/protocol/openid-connect/token", form, authenticated=False
        )
        self.token = result.get("access_token", "")
        if not self.token:
            raise Refused("authentication_failed")

    def request(self, method: str, path: str, data=None, *, authenticated: bool = True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = json.dumps(data).encode() if authenticated and data is not None else data
        req = urllib.request.Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=15) as response:
                raw = response.read(1048577)
                if len(raw) > 1048576:
                    raise Refused("response_too_large")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            # Neither response bodies nor exception strings reach the operator.
            if error.code == 409:
                raise Refused("conflict", 21) from None
            raise Refused("keycloak_request_failed") from None
        except (urllib.error.URLError, ValueError, OSError):
            raise Refused("keycloak_request_failed") from None

    def call(self, method: str, path: str = "", data=None):
        return self.request(method, self.root + path, data)

    def pages(self, path: str):
        separator = "&" if "?" in path else "?"
        for first in range(0, 1000000, 100):
            batch = self.call("GET", f"{path}{separator}first={first}&max=100")
            if not isinstance(batch, list):
                raise Refused("invalid_response")
            yield from batch
            if not batch:
                return
        raise Refused("listing_limit_reached")
