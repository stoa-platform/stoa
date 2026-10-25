"""OIDC flows, redirects and effective mapper rules."""

import re

from keycloak_audit_lib.common import API_CLIENTS, ATTR_BOUNDS, bounded, is_true


def client_rules(self, path, text, obj, start, emit, env, inherited):
    if "clientId" in obj and any(
        k in obj
        for k in (
            "publicClient",
            "standardFlowEnabled",
            "serviceAccountsEnabled",
            "redirectUris",
            "grantTypes",
        )
    ):
        saml = obj.get("protocol") == "saml"
        if not saml:
            grants = obj.get("grantTypes", [])
            if is_true(obj.get("implicitFlowEnabled")) or "implicit" in grants:
                emit("KC_IMPLICIT", "Flux implicite activé.", "implicitFlowEnabled")
            if is_true(obj.get("directAccessGrantsEnabled")) or "password" in grants:
                emit(
                    "KC_DIRECT_GRANT",
                    "Direct grant activé.",
                    "directAccessGrantsEnabled",
                    dev_warning=True,
                )
            if (
                is_true(obj.get("publicClient"))
                and obj.get("standardFlowEnabled", True) is not False
            ):
                pkce_attrs = obj.get("attributes", {})
                pkce = (
                    pkce_attrs.get("pkce.code.challenge.method")
                    if isinstance(pkce_attrs, dict)
                    else None
                )
                if pkce != "S256" and not (
                    obj.get("pkce") is True and obj.get("pkceCodeChallengeMethod") == "S256"
                ):
                    emit("KC_PKCE", "PKCE S256 non imposé côté serveur.", "publicClient")
            if is_true(obj.get("publicClient")) and obj.get("serviceAccountsEnabled") is True:
                emit(
                    "KC_PUBLIC_SERVICE_ACCOUNT",
                    "Compte de service sur client public.",
                    "publicClient",
                )
        for key in ("redirectUris", "webOrigins"):
            values = obj.get(key, [])
            if not isinstance(values, list):
                emit("KC_UNRESOLVED", "Liste de redirections ou origines non résolue.", key)
                continue
            if any("*" in str(v) for v in values):
                emit(
                    "KC_REDIRECT_WILDCARD",
                    "Redirection ou origine générique.",
                    key,
                    dev_warning=not is_true(obj.get("publicClient")),
                )
            if env == "prod" and any(re.match(r"http://", str(v)) for v in values):
                emit("KC_REDIRECT_HTTP", "URI HTTP dans une représentation de production.", key)
            if env == "prod" and any(
                re.search(r"(?i)localhost|127\.0\.0\.1|\[::1\]", str(v)) for v in values
            ):
                emit("KC_PROD_LOOPBACK", "URI locale dans une représentation de production.", key)
        attrs = obj.get("attributes", {})
        if not isinstance(attrs, dict):
            emit("KC_UNRESOLVED", "Attributs client dynamiques.", "attributes")
            attrs = {}
        for key, maximum in ATTR_BOUNDS.items():
            if key in attrs and not bounded(attrs[key], maximum):
                emit("KC_CLIENT_LIFETIME", "Surcharge client non bornée ou trop longue.", key)
        if "*" in str(attrs.get("post.logout.redirect.uris", "")):
            emit(
                "KC_LOGOUT_WILDCARD",
                "Redirection de déconnexion générique.",
                "post.logout.redirect.uris",
            )
        effective = list(obj.get("protocolMappers", []))
        for scope in obj.get("defaultClientScopes", []):
            effective += (inherited or {}).get(scope, {}).get("protocolMappers", [])
        if obj.get("clientId") in API_CLIENTS and obj.get("bearerOnly") is not True:
            if not any(
                m.get("protocolMapper") == "oidc-audience-mapper"
                and is_true(m.get("config", {}).get("access.token.claim"))
                and m.get("config", {}).get("included.client.audience") == "control-plane-api"
                for m in effective
                if isinstance(m, dict)
            ):
                emit(
                    "KC_AUDIENCE",
                    "Audience API explicite absente des mappers et scopes par défaut.",
                    "clientId",
                    severity="REVIEW" if "grantTypes" in obj else "HIGH",
                )
            if not any(
                m.get("config", {}).get("claim.name") == "tenant_id"
                and is_true(m.get("config", {}).get("access.token.claim"))
                for m in effective
                if isinstance(m, dict)
            ):
                emit(
                    "KC_TENANT_MISSING",
                    "Claim tenant_id absent des mappers et scopes par défaut.",
                    "clientId",
                    severity="REVIEW"
                    if "grantTypes" in obj or obj.get("serviceAccountsEnabled") is True
                    else "HIGH",
                )
