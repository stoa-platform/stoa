"""Transport contracts without a network connection."""

import importlib.util
import io
import json
import secrets
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

MODULES = Path(__file__).resolve().parents[2] / "charts/stoa-platform/files/first_admin"
spec = importlib.util.spec_from_file_location("first_admin_transport", MODULES / "transport.py")
transport = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transport
spec.loader.exec_module(transport)


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class TransportTests(unittest.TestCase):
    def make_client(self, opener):
        with patch.object(transport.urllib.request, "build_opener", return_value=opener):
            return transport.Keycloak(
                "http://keycloak:8080", "stoa", "operator", secrets.token_urlsafe()
            )

    def test_credentials_are_encoded_in_body_and_token_only_in_header(self):
        token = secrets.token_urlsafe()
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append(request)
                return Reply(json.dumps({"access_token": token}).encode())

        client = self.make_client(Opener())
        client.call("GET", "/users")
        self.assertNotIn(token, calls[1].full_url)
        self.assertEqual("Bearer " + token, calls[1].headers["Authorization"])
        self.assertNotIn("password=", calls[0].full_url)

    def test_http_errors_do_not_include_response_or_token(self):
        token = secrets.token_urlsafe()

        class Opener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 400, token, {}, Reply(token.encode())
                )

        with self.assertRaises(transport.Refused) as caught:
            self.make_client(Opener())
        self.assertNotIn(token, str(caught.exception))

    def test_redirects_are_refused(self):
        with self.assertRaises(transport.Refused):
            transport.NoRedirect().redirect_request(None, None, 302, "", {}, "http://other.test")

    def test_response_size_is_bounded(self):
        class Opener:
            def open(self, request, timeout):
                return Reply(b" " * 1048577)

        with self.assertRaisesRegex(transport.Refused, "response_too_large"):
            self.make_client(Opener())
