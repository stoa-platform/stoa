"""Explicit policy validation and mapper presets."""

import json
from pathlib import Path

from keycloak_migration.core import (
    MAX_BYTES,
    MigrationError,
    exact_uri,
    identifier,
    keys,
    require,
    strings,
)


def mapper(preset, name):
    base = {"name": name, "protocol": "openid-connect", "consentRequired": False}
    if preset == "audience":
        return dict(
            base,
            protocolMapper="oidc-audience-mapper",
            config={
                "included.client.audience": "control-plane-api",
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        )
    require(preset == "tenant")
    return dict(
        base,
        protocolMapper="oidc-usermodel-attribute-mapper",
        config={
            "user.attribute": "tenant_id",
            "claim.name": "tenant_id",
            "jsonType.label": "String",
            "multivalued": "false",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true",
        },
    )


def validate_policy(p):
    keys(
        p,
        (
            "version",
            "realm",
            "reset_password_allowed",
            "tenant_attribute_reviewed",
            "clients",
            "reviewed_clients",
            "scopes",
            "idps",
        ),
    )
    require(type(p["version"]) is int and p["version"] == 1)
    identifier(p["realm"])
    require(p["realm"] != "master", "The administrative realm is excluded")
    require(type(p["reset_password_allowed"]) is bool)
    require(type(p["tenant_attribute_reviewed"]) is bool)
    strings(p["reviewed_clients"])
    strings(p["idps"])
    require(isinstance(p["clients"], dict) and isinstance(p["scopes"], dict))
    require(not set(p["clients"]) & set(p["reviewed_clients"]))
    for name, client in p["clients"].items():
        identifier(name)
        keys(
            client,
            ("browser", "redirect_uris", "web_origins", "post_logout_redirect_uris", "mappers"),
        )
        require(type(client["browser"]) is bool)
        for field in ("redirect_uris", "web_origins", "post_logout_redirect_uris"):
            values = client[field]
            require(isinstance(values, list) and all(isinstance(v, str) for v in values))
            require(len(values) == len(set(values)))
            require(bool(values) == client["browser"])
            for value in values:
                exact_uri(value, origin=field == "web_origins")
    definitions = list(p["scopes"].items()) + [(n, c["mappers"]) for n, c in p["clients"].items()]
    for target, definitions_for_target in definitions:
        identifier(target)
        require(isinstance(definitions_for_target, dict))
        for name, preset in definitions_for_target.items():
            identifier(name)
            mapper(preset, name)
            require(
                preset != "tenant" or p["tenant_attribute_reviewed"],
                "Tenant attributes must be reviewed before changing tenant claims",
            )
    return p


def read_policy(path):
    try:
        raw = Path(path).read_bytes()
        require(len(raw) <= MAX_BYTES)

        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "Duplicate JSON key in policy")
                result[key] = value
            return result

        return validate_policy(json.loads(raw, object_pairs_hook=unique))
    except MigrationError:
        raise
    except (OSError, ValueError, TypeError):
        raise MigrationError("Cannot read a valid policy; details withheld") from None
