"""Declarative bounds and nested representation traversal."""

import json
import re

from keycloak_audit_lib.common import ATTR_BOUNDS, bounded, walk


def inspect_representations(self, path, text, representations):
    visited = set()
    for representation, start in representations:
        if not isinstance(representation, (list, dict)):
            continue
        for obj in walk(representation):
            for attributes_key in ("keycloakAttributes",):
                attrs = obj.get(attributes_key, {})
                if isinstance(attrs, dict):
                    for key, maximum in ATTR_BOUNDS.items():
                        if key in attrs and not bounded(attrs[key], maximum):
                            self.add(
                                path,
                                text,
                                "KC_CLIENT_LIFETIME",
                                "Surcharge déclarative non bornée ou trop longue.",
                                key,
                                start,
                            )
            times = obj.get("tokenLifespans", {})
            if isinstance(times, dict):
                for key, maximum in [
                    ("accessToken", 300),
                    ("idToken", 300),
                    ("refreshToken", 28800),
                ]:
                    if key in times and not bounded(times[key], maximum):
                        self.add(
                            path,
                            text,
                            "KC_DECLARED_LIFETIME",
                            "Durée déclarative supérieure au plafond.",
                            key,
                            start,
                        )
            defaults = obj.get("clientDefaults", {})
            if isinstance(defaults, dict):
                for key, maximum in [
                    ("accessTokenLifespan", 300),
                    ("refreshTokenLifespan", 28800),
                ]:
                    if key in defaults and not bounded(defaults[key], maximum):
                        self.add(
                            path,
                            text,
                            "KC_DECLARED_LIFETIME",
                            "Durée déclarative supérieure au plafond.",
                            key,
                            start,
                        )
            for key, value in obj.items():
                if (
                    re.search(
                        r"(?i)^(?:KC|KEYCLOAK).*?(?:PASSWORD|SECRET)$|^client[-_]secret$",
                        str(key),
                    )
                    and isinstance(value, str)
                    and value
                    and not re.search(r"\$|REPLACE_|CHANGE_ME|<[^>]+>", value)
                ):
                    self.add(
                        path,
                        text,
                        "KC_HARDCODED_SECRET",
                        "Valeur sensible littérale [MASQUÉE].",
                        key,
                        start,
                        dev_warning=True,
                    )
            is_realm = "realm" in obj and ("enabled" in obj or "clients" in obj)
            is_client = "clientId" in obj
            # Children of a realm are checked with inherited default scopes.
            if (
                not is_realm
                and not is_client
                and not any(k in obj for k in ("protocolMappers", "claim.name"))
            ):
                continue
            signature = json.dumps(obj, sort_keys=True)
            if signature in visited:
                continue
            if is_realm:
                for c in obj.get("clients", []):
                    visited.add(json.dumps(c, sort_keys=True))
            visited.add(signature)
            self.representation(
                path, text, obj, self.object_line(text, obj, start), full_realm=is_realm
            )
