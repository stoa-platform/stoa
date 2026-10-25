"""Stateful in-memory admin API double."""

from urllib.parse import parse_qs, urlsplit


class FakeKeycloak:
    def __init__(self):
        self.realm = {"attributes": {"preserved": "yes"}}
        self.users = []
        self.clients = []
        self.roles = {}
        self.groups = {}
        self.service_accounts = {}
        self.parent_groups = {}
        self.writes = []
        self.interrupt_after = None

    def pages(self, path):
        return iter(self.call("GET", path))

    def call(self, method, path="", data=None):
        parsed = urlsplit(path)
        query = parse_qs(parsed.query)
        route = parsed.path
        if method == "GET":
            if route == "":
                return {**self.realm, "attributes": dict(self.realm["attributes"])}
            if route == "/roles/cpi-admin/users":
                return []
            if route.endswith("/service-account-user"):
                return self.service_accounts[route.split("/")[2]]
            if route == "/clients":
                return self.clients
            if route == "/users":
                return [u for u in self.users if not query or u["username"] == query["username"][0]]
            if route.endswith("/groups"):
                return self.groups.get(route.split("/")[2], [])
            if route.endswith("/composite"):
                return self.roles.get(route, [])
            if route.startswith("/groups/"):
                return self.parent_groups.get(route.split("/")[2], {"id": route.split("/")[2]})
            if route == "/roles/cpi-admin":
                return {"id": "admin-role", "name": "cpi-admin"}
            if route == "/authentication/required-actions":
                return [{"alias": "CONFIGURE_TOTP", "enabled": True, "defaultAction": True}]
            raise AssertionError((method, path))
        self.writes.append((method, path))
        if route == "/clients":
            self.clients.append({**data, "id": "claim"})
        elif route == "":
            self.realm.update(data)
        elif route == "/users":
            self.users.append({**data, "id": "new-user"})
        elif route.endswith("/role-mappings/realm"):
            self.roles[route + "/composite"] = data
        else:
            raise AssertionError((method, path))
        if len(self.writes) == self.interrupt_after:
            raise InterruptedError
