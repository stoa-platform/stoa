"""Read-only complete migration planning."""

from keycloak_migration.core import BOUNDS, CLIENT_BOUNDS, identifier, require
from keycloak_migration.operations import field_op, index, reconcile_mappers, validate_effective


def plan(api, p):
    """Complete all reads/validation before any write. No user or credential endpoints."""
    realm = api.get("")
    require(isinstance(realm, dict) and realm.get("realm") == p["realm"])
    clients = index(api.clients(), "clientId")
    require(
        set(clients) == set(p["clients"]) | set(p["reviewed_clients"]),
        "Client inventory differs from policy; nothing applied",
    )
    idps = index(api.get("/identity-provider/instances"), "alias")
    require(set(idps) == set(p["idps"]), "IdP inventory differs from policy; nothing applied")
    scopes = index(api.get("/client-scopes"), "name")
    require(set(p["scopes"]) <= set(scopes), "A managed client scope is missing")
    ops = []
    desired = dict(BOUNDS, resetPasswordAllowed=p["reset_password_allowed"])
    # Duration values are ceilings: never lengthen an already stricter bound.
    for key, ceiling in BOUNDS.items():
        old = realm.get(key)
        if type(ceiling) is int and ceiling > 0 and type(old) is int and old > 0:
            desired[key] = min(old, ceiling)
    for idle, maximum in (
        ("ssoSessionIdleTimeout", "ssoSessionMaxLifespan"),
        ("ssoSessionIdleTimeoutRememberMe", "ssoSessionMaxLifespanRememberMe"),
        ("clientSessionIdleTimeout", "clientSessionMaxLifespan"),
        ("offlineSessionIdleTimeout", "offlineSessionMaxLifespan"),
    ):
        desired[idle] = min(desired[idle], desired[maximum])
    desired_realm = desired.copy()
    op = field_op("", realm, [([k], v) for k, v in desired.items()])
    if op:
        ops.append(op)
    # Close brokered admission before configuring clients/mappers.
    for alias in sorted(p["idps"]):
        path = "/identity-provider/instances/" + identifier(alias)
        current = api.get(path)
        require(current.get("alias") == alias)
        op = field_op(path, current, [(["enabled"], False)])
        if op:
            ops.append(op)
    # A shared mapper update must not silently affect an exempt client.
    managed_scope_ids = {scopes[n]["id"] for n in p["scopes"]}
    if managed_scope_ids:
        for name in p["reviewed_clients"]:
            path = "/clients/" + identifier(clients[name]["id"])
            for category in ("default", "optional"):
                attached = api.get(path + "/" + category + "-client-scopes")
                require(isinstance(attached, list))
                require(
                    not managed_scope_ids & {s["id"] for s in attached},
                    "Managed scope affects an exempt client; explicitly manage that client first",
                )
    scope_cache = {}
    for name, definitions in sorted(p["scopes"].items()):
        path = "/client-scopes/" + identifier(scopes[name]["id"]) + "/protocol-mappers/models"
        additions, future = reconcile_mappers(api, path, definitions)
        ops.extend(additions)
        scope_cache[scopes[name]["id"]] = future
    for name, settings in sorted(p["clients"].items()):
        path = "/clients/" + identifier(clients[name]["id"])
        current = api.get(path)
        require(
            current.get("clientId") == name and current.get("protocol") == "openid-connect",
            "A managed client is missing or is not OIDC",
        )
        attrs = dict(CLIENT_BOUNDS)
        relation = {
            "access.token.lifespan": "accessTokenLifespan",
            "client.session.idle.timeout": "clientSessionIdleTimeout",
            "client.session.max.lifespan": "clientSessionMaxLifespan",
            "client.offline.session.idle.timeout": "offlineSessionIdleTimeout",
            "client.offline.session.max.lifespan": "offlineSessionMaxLifespan",
        }
        for key, realm_key in relation.items():
            attrs[key] = str(min(int(attrs[key]), desired_realm[realm_key]))
        for key, ceiling in attrs.copy().items():
            old = current.get("attributes", {}).get(key)
            if isinstance(old, str) and old.isascii() and old.isdigit() and int(old) > 0:
                attrs[key] = str(min(int(old), int(ceiling)))
        for idle, maximum in (
            ("client.session.idle.timeout", "client.session.max.lifespan"),
            ("client.offline.session.idle.timeout", "client.offline.session.max.lifespan"),
        ):
            attrs[idle] = str(min(int(attrs[idle]), int(attrs[maximum])))
        attrs["post.logout.redirect.uris"] = "##".join(settings["post_logout_redirect_uris"])
        if settings["browser"]:
            attrs["pkce.code.challenge.method"] = "S256"
        desired = {
            "redirectUris": settings["redirect_uris"],
            "webOrigins": settings["web_origins"],
            "standardFlowEnabled": settings["browser"],
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
        }
        op = field_op(
            path,
            current,
            [([k], v) for k, v in desired.items()]
            + [(["attributes", k], v) for k, v in attrs.items()],
        )
        if op:
            ops.append(op)
        additions, effective = reconcile_mappers(
            api, path + "/protocol-mappers/models", settings["mappers"]
        )
        ops.extend(additions)
        required = list(effective)
        seen = set()
        for category in ("default", "optional"):
            entries = api.get(path + "/" + category + "-client-scopes")
            require(isinstance(entries, list))
            for scope in entries:
                sid = scope["id"]
                if sid in seen:
                    continue
                seen.add(sid)
                if sid not in scope_cache:
                    collection = "/client-scopes/" + identifier(sid) + "/protocol-mappers/models"
                    scope_cache[sid] = list(index(api.get(collection), "name").values())
                effective.extend(scope_cache[sid])
                if category == "default":
                    required.extend(scope_cache[sid])
        validate_effective(effective)
        if settings["browser"]:
            require(
                any(
                    x.get("config", {}).get("included.client.audience") == "control-plane-api"
                    for x in required
                ),
                "Browser client lacks an API audience mapper",
            )
            require(
                any(x.get("config", {}).get("claim.name") == "tenant_id" for x in required),
                "Browser client lacks a tenant mapper",
            )
    return ops
