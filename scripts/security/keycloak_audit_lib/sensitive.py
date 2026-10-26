"""Sensitive values and tenant provenance checks."""

import re

from keycloak_audit_lib.common import walk


def secret_rules(self, path, text, obj, start, emit):
    # Credential values are NEVER copied into findings or inventory.
    for node in walk(obj):
        for key in ("secret", "clientSecret", "password", "bindCredential"):
            value = node.get(key)
            values = value if isinstance(value, list) else [value]
            if any(
                isinstance(v, str) and v and not re.search(r"\$|REPLACE_|CHANGE_ME|<[^>]+>", v)
                for v in values
            ):
                emit(
                    "KC_HARDCODED_SECRET",
                    "Valeur sensible littérale [MASQUÉE].",
                    key,
                    dev_warning=True,
                )
        if node.get("type") == "password" and node.get("value"):
            emit(
                "KC_USER_PASSWORD",
                "Mot de passe utilisateur importé [MASQUÉ].",
                "value",
                dev_warning=True,
            )
        if node.get("claim.name") == "tenant_id":
            node_start = self.object_line(text, node, start)
            if node.get("user.attribute") == "tenant":
                self.add(
                    path,
                    text,
                    "KC_TENANT_ATTRIBUTE",
                    "Mapper tenant au lieu de tenant_id ; harmoniser les producteurs.",
                    "user.attribute",
                    node_start,
                )
            if node.get("claim.value") is not None:
                self.add(
                    path,
                    text,
                    "KC_TENANT_TRUST",
                    "Tenant fixé par mapper : vérifier la provenance autorisée.",
                    "claim.value",
                    node_start,
                    severity="REVIEW",
                )
