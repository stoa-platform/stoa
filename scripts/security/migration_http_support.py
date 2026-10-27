"""Synthetic HTTP boundary for offline migration contracts."""

import copy
import json

from keycloak_migration import core as m

SECRET = "SYNTHETIC-CANARY-DO-NOT-LOG"
ROOT = "/admin/realms/example"


def policy():
    return {
        "version": 1,
        "realm": "example",
        "reset_password_allowed": False,
        "tenant_attribute_reviewed": True,
        "reviewed_clients": ["account"],
        "idps": ["social"],
        "scopes": {},
        "clients": {
            "portal": {
                "browser": True,
                "redirect_uris": [
                    "https://portal.example.invalid",
                    "https://portal.example.invalid/",
                ],
                "web_origins": ["https://portal.example.invalid"],
                "post_logout_redirect_uris": ["https://portal.example.invalid/"],
                "mappers": {"api-audience": "audience", "tenant-id": "tenant"},
            }
        },
    }


class Response:
    def __init__(self, status, data):
        self.status = status
        self.body = json.dumps(data).encode() if data is not None else b""

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class FakeKeycloak:
    """No sockets, including tests of the actual HTTPS adapter."""

    def __init__(self):
        self.objects = {
            ROOT: {
                **{k: (v * 2 if type(v) is int else not v) for k, v in m.BOUNDS.items()},
                "realm": "example",
                "registrationAllowed": True,
                "resetPasswordAllowed": True,
                "smtpServer": {"password": SECRET},
            },
            ROOT + "/clients": [
                {"id": "c1", "clientId": "portal", "protocol": "openid-connect"},
                {"id": "c0", "clientId": "account", "protocol": "openid-connect"},
            ],
            ROOT + "/clients/c1": {
                "id": "c1",
                "clientId": "portal",
                "protocol": "openid-connect",
                "publicClient": True,
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": True,
                "redirectUris": ["https://old.example.invalid/*?token=" + SECRET],
                "webOrigins": ["*"],
                "secret": SECRET,
                "attributes": {"unrelated": SECRET, "post.logout.redirect.uris": "+"},
            },
            ROOT + "/clients/c1/protocol-mappers/models": [],
            ROOT + "/clients/c1/default-client-scopes": [],
            ROOT + "/clients/c1/optional-client-scopes": [],
            ROOT + "/client-scopes": [],
            ROOT + "/clients/c0/default-client-scopes": [],
            ROOT + "/clients/c0/optional-client-scopes": [],
            ROOT + "/identity-provider/instances": [{"alias": "social", "providerId": "google"}],
            ROOT + "/identity-provider/instances/social": {
                "alias": "social",
                "providerId": "google",
                "enabled": True,
                "firstBrokerLoginFlowAlias": "first broker login",
                "config": {"clientSecret": SECRET},
            },
        }
        self.requests = []
        self.writes = []
        self.fail_write = None
        self.fail_status = 503
        self.ignore_write = False
        self.lost_response = False
        self.next_id = 0

    def connection(self, *args, **kwargs):
        fake = self

        class Connection:
            def request(self, method, url, body=None, headers=None):
                self.args = method, url, body, headers

            def getresponse(self):
                method, url, body, headers = self.args
                self.response = fake.request(method, url, body, headers)
                return self.response

            def close(self):
                pass

        return Connection()

    def request(self, method, url, body, headers):
        assert headers["Authorization"] == "Bearer " + SECRET
        self.requests.append((method, url))
        if method == "GET" and url.startswith(ROOT + "/clients?"):
            from urllib.parse import parse_qs, urlsplit

            params = parse_qs(urlsplit(url).query)
            first, maximum = int(params["first"][0]), int(params["max"][0])
            return Response(
                200, copy.deepcopy(self.objects[ROOT + "/clients"][first : first + maximum])
            )
        if method == "GET":
            if url not in self.objects:
                return Response(404, {"error": SECRET})
            return Response(200, copy.deepcopy(self.objects[url]))
        self.writes.append((method, url))
        if self.fail_write == len(self.writes):
            return Response(self.fail_status, {"error": SECRET})
        data = json.loads(body) if body else None
        if not self.ignore_write:
            if method == "PUT":
                if url in self.objects:
                    self.objects[url].update(data)
                else:
                    collection, ident = url.rsplit("/", 1)
                    mapper = next(x for x in self.objects[collection] if x["id"] == ident)
                    mapper.update(data)
            elif method == "POST":
                self.next_id += 1
                data["id"] = f"mapper-{self.next_id}"
                self.objects[url].append(data)
            elif method == "DELETE":
                collection, ident = url.rsplit("/", 1)
                self.objects[collection] = [x for x in self.objects[collection] if x["id"] != ident]
        if self.lost_response:
            self.lost_response = False
            raise OSError(SECRET)
        return Response(201 if method == "POST" else 204, None)
