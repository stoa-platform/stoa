#!/usr/bin/env python3
"""Check tenant claims using only a disposable local Keycloak 26.5.3 container."""

import base64
import json
import os
import secrets
import subprocess
import sys
import time
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "quay.io/keycloak/keycloak:26.5.3"
REALM = "tenant-claim-check"
PROFILE_PROVIDER = "org.keycloak.userprofile.UserProfileProvider"
HTTP = build_opener(ProxyHandler({}))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def docker(*args, context=None, env=None):
    command = ["docker"] + (["--context", context] if context else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=180)
    require(result.returncode == 0, "Docker operation failed")
    return result.stdout.strip()


def request(base, path, *, token=None, form=None, body=None, method=None, allowed=(200,)):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        response = HTTP.open(Request(base + path, data, headers, method=method), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        require(response.status in allowed, f"Unexpected HTTP status {response.status}")
        raw = response.read()
        return response.status, json.loads(raw) if raw else None


def fixture(password):
    source = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
    mapper = json.loads((ROOT / "deploy/keycloak/tenant-id-mapper.json").read_text())
    profile = json.loads(
        source["components"][PROFILE_PROVIDER][0]["config"]["kc.user.profile.config"][0]
    )
    tenant = next(item for item in profile["attributes"] if item["name"] == "tenant_id")
    require(
        tenant["permissions"] == {"view": ["admin"], "edit": ["admin"]},
        "Repository tenant_id profile must be admin-only",
    )
    require(tenant.get("multivalued") is False, "Repository tenant_id must be single-valued")
    users = []
    for name in ("assigned", "unassigned", "inherited"):
        users.append(
            {
                "username": name,
                "enabled": True,
                "email": name + "@example.test",
                "emailVerified": True,
                "firstName": "Fixture",
                "lastName": "User",
                "credentials": [{"type": "password", "value": password, "temporary": False}],
                "attributes": {"tenant_id": ["direct-value"]} if name == "assigned" else {},
                "groups": ["/guarded-group"] if name == "inherited" else [],
                "clientRoles": {"account": ["manage-account", "view-profile"]},
            }
        )
    return {
        "realm": REALM,
        "enabled": True,
        "sslRequired": "none",
        "users": users,
        "components": {PROFILE_PROVIDER: source["components"][PROFILE_PROVIDER]},
        # This deliberately invalid group fixture documents the static guard's boundary.
        "groups": [{"name": "guarded-group", "attributes": {"tenant_id": ["group-value"]}}],
        "clients": [
            {
                "clientId": "claim-check",
                "enabled": True,
                "publicClient": True,
                "directAccessGrantsEnabled": True,
                "defaultClientScopes": ["profile", "roles"],
                "protocol": "openid-connect",
                "protocolMappers": [mapper],
            }
        ],
    }


def claims(base, username, password):
    path = f"/realms/{REALM}/protocol/openid-connect"
    _, tokens = request(
        base,
        path + "/token",
        form={
            "grant_type": "password",
            "client_id": "claim-check",
            "username": username,
            "password": password,
            "scope": "openid",
        },
    )
    decoded = []
    for name in ("access_token", "id_token"):
        payload = tokens[name].split(".")[1]
        decoded.append(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))))
    _, userinfo = request(base, path + "/userinfo", token=tokens["access_token"])
    return tokens["access_token"], [*decoded, userinfo]


def verify(base, password, admin_password):
    _, admin = request(
        base,
        "/realms/master/protocol/openid-connect/token",
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "fixture-admin",
            "password": admin_password,
        },
    )
    admin_token = admin["access_token"]
    _, server = request(base, "/admin/serverinfo", token=admin_token)
    require(server["systemInfo"]["version"] == "26.5.3", "Keycloak version mismatch")
    realm = fixture(password)
    request(base, "/admin/realms", token=admin_token, body=realm, allowed=(201,))
    _, profile = request(base, f"/admin/realms/{REALM}/users/profile", token=admin_token)
    expected = json.loads(
        realm["components"][PROFILE_PROVIDER][0]["config"]["kc.user.profile.config"][0]
    )
    tenant = next(item for item in profile["attributes"] if item["name"] == "tenant_id")
    require(
        tenant == next(item for item in expected["attributes"] if item["name"] == "tenant_id"),
        "Imported tenant_id profile differs from the repository",
    )
    require(
        profile.get("unmanagedAttributePolicy") == expected.get("unmanagedAttributePolicy"),
        "Imported unmanaged attribute policy differs from the repository",
    )
    print("Keycloak 26.5.3: disposable local fixture; imported profile verified")
    for name, expected in (
        ("assigned", "direct-value"),
        ("unassigned", None),
        ("inherited", "group-value"),
    ):
        _, outputs = claims(base, name, password)
        require(
            all(output.get("tenant_id") == expected for output in outputs),
            "Unexpected tenant claim value",
        )
        if expected is None:
            require(all("tenant_id" not in output for output in outputs), "Absent claim expected")
        label = "known guarded limitation" if name == "inherited" else "verified"
        print(f"PASS {name}: access token, ID token and userinfo ({label})")

    token, _ = claims(base, "assigned", password)
    account = f"/realms/{REALM}/account/"
    _, user = request(base, account, token=token)
    user.pop("userProfileMetadata", None)
    user["firstName"] = "AllowedChange"
    request(base, account, token=token, body=user, allowed=(204,))
    users_path = f"/admin/realms/{REALM}/users"
    _, matches = request(base, users_path + "?username=assigned&exact=true", token=admin_token)
    user_path = users_path + "/" + matches[0]["id"]
    _, persisted = request(base, user_path, token=admin_token)
    require(persisted["firstName"] == "AllowedChange", "Account write control failed")
    user.setdefault("attributes", {})["tenant_id"] = ["attempted-value"]
    status, _ = request(base, account, token=token, body=user, allowed=(204, 400))
    _, persisted = request(base, user_path, token=admin_token)
    require(
        persisted.get("attributes", {}).get("tenant_id") == ["direct-value"],
        "Account API changed tenant_id",
    )
    print(
        f"PASS account API: allowed write verified; tenant_id unchanged via admin reread (HTTP {status})"
    )


def main():
    context = docker("context", "show")
    endpoint = json.loads(docker("context", "inspect", context))[0]["Endpoints"]["docker"]["Host"]
    require(endpoint.startswith(("unix://", "npipe://")), "Only a local Docker context is allowed")
    password, admin_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    name = "tenant-claim-check-" + secrets.token_hex(6)
    env = {
        **os.environ,
        "KC_BOOTSTRAP_ADMIN_USERNAME": "fixture-admin",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
    }
    try:
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--publish",
            "127.0.0.1::8080",
            "--env",
            "KC_BOOTSTRAP_ADMIN_USERNAME",
            "--env",
            "KC_BOOTSTRAP_ADMIN_PASSWORD",
            IMAGE,
            "start-dev",
            context=context,
            env=env,
        )
        bindings = json.loads(
            docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", name, context=context)
        )["8080/tcp"]
        require(
            len(bindings) == 1 and bindings[0]["HostIp"] == "127.0.0.1",
            "Container must be bound only to loopback",
        )
        base = "http://127.0.0.1:" + bindings[0]["HostPort"]
        deadline = time.monotonic() + 120
        while True:
            try:
                request(base, "/realms/master/.well-known/openid-configuration")
                break
            except (URLError, RuntimeError, OSError, HTTPException):
                require(time.monotonic() < deadline, "Disposable Keycloak startup timed out")
                time.sleep(1)
        verify(base, password, admin_password)
    finally:
        docker("rm", "--force", name, context=context)
    print("PASS cleanup: disposable container removed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never emit HTTP bodies, Docker logs, credentials, tokens or local endpoints.
        print(f"FAIL tenant claim behaviour ({type(error).__name__})", file=sys.stderr)
        sys.exit(1)
