"""Single-use administrator provisioning against the Keycloak admin API."""

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from transport import Refused

MARKER = "stoa-first-admin-bootstrap"
CONSUMED = "stoa.firstAdmin.consumedAt"


def now() -> str:
    return datetime.now(UTC).isoformat()


def administrators(kc):
    """Include service accounts and roles inherited through groups/composites."""
    direct = next(iter(kc.pages("/roles/cpi-admin/users")), None)
    if direct:
        return direct["id"]
    # Some Keycloak versions omit service accounts from the general user list.
    subjects = {user["id"]: user for user in kc.pages("/users")}
    for client in kc.pages("/clients"):
        if client.get("serviceAccountsEnabled"):
            user = kc.call("GET", f"/clients/{client['id']}/service-account-user")
            subjects[user["id"]] = user
    for user in subjects.values():
        paths = [f"/users/{user['id']}/role-mappings/realm/composite"]
        seen = set()
        for group in kc.pages(f"/users/{user['id']}/groups"):
            while group and group["id"] not in seen:
                seen.add(group["id"])
                paths.append(f"/groups/{group['id']}/role-mappings/realm/composite")
                detail = kc.call("GET", f"/groups/{group['id']}")
                parent = detail.get("parentId")
                group = {"id": parent} if parent else None
        for path in paths:
            if any(role["name"] == "cpi-admin" for role in kc.call("GET", path)):
                return user["id"]
    return None


def provision(kc, identity: dict) -> tuple[int, str, str | None]:
    realm = kc.call("GET")
    if realm.get("attributes", {}).get(CONSUMED):
        return 10, "already_consumed", None
    admin = administrators(kc)
    if admin:
        return 20, "administrator_exists", admin

    username, email = identity["username"], identity["email"]
    fingerprint = hashlib.sha256(
        json.dumps([username, email, identity["bootstrap_id"]]).encode()
    ).hexdigest()
    clients = kc.call("GET", "/clients?" + urlencode({"clientId": MARKER}))
    users = kc.call("GET", "/users?" + urlencode({"username": username, "exact": "true"}))
    if not clients:
        if users:
            raise Refused("identity_exists", 21)
        # Keycloak enforces unique clientId: competing requests cannot both claim.
        kc.call(
            "POST",
            "/clients",
            {
                "clientId": MARKER,
                "enabled": False,
                "attributes": {"request": fingerprint, "startedAt": now()},
            },
        )
        clients = kc.call("GET", "/clients?" + urlencode({"clientId": MARKER}))
    if len(clients) != 1 or clients[0].get("attributes", {}).get("request") != fingerprint:
        raise Refused("different_request_pending", 21)
    if not users:
        actions = kc.call("GET", "/authentication/required-actions")
        required = {a["alias"] for a in actions if a.get("enabled") and a.get("defaultAction")}
        required.add("UPDATE_PASSWORD")
        kc.call("PUT", "", {"adminEventsEnabled": True, "adminEventsDetailsEnabled": False})
        kc.call(
            "POST",
            "/users",
            {
                "username": username,
                "email": email,
                "enabled": True,
                "requiredActions": sorted(required),
                "credentials": [
                    {"type": "password", "value": identity["initial_password"], "temporary": True}
                ],
            },
        )
        users = kc.call("GET", "/users?" + urlencode({"username": username, "exact": "true"}))
    if len(users) != 1 or users[0].get("username") != username or users[0].get("email") != email:
        raise Refused("identity_conflict", 21)
    user_id = users[0]["id"]
    # Re-check before granting privileges if an external writer changed the realm.
    admin = administrators(kc)
    if admin:
        return 20, "administrator_exists", admin
    role = kc.call("GET", "/roles/cpi-admin")
    kc.call("POST", f"/users/{user_id}/role-mappings/realm", [role])
    attributes = kc.call("GET").get("attributes", {})
    attributes[CONSUMED] = now()
    kc.call(
        "PUT",
        "",
        {
            "attributes": attributes,
            "adminEventsEnabled": True,
            "adminEventsDetailsEnabled": False,
        },
    )
    return 0, "created", user_id
