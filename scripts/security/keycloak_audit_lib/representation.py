"""Representation normalization and rule dispatch."""

import json
import re

from keycloak_audit_lib.client import client_rules
from keycloak_audit_lib.common import environment
from keycloak_audit_lib.realm import realm_rules
from keycloak_audit_lib.sensitive import secret_rules


class RepresentationRules:
    def representation(self, path, text, obj, start=1, full_realm=False, inherited=None):
        obj = dict(obj)

        def emit(rule, msg, key="", **kw):
            return self.add(path, text, rule, msg, key, start, **kw)

        env = environment(path, self.mode)
        for key in (
            "clients",
            "clientScopes",
            "users",
            "protocolMappers",
            "defaultClientScopes",
            "grantTypes",
        ):
            if key in obj and not isinstance(obj[key], list):
                self.errors = True
                emit("KC_PARSE", "Collection mal formée ; détails masqués.", key, severity="ERROR")
                obj[key] = []
        for mapper_obj in obj.get("protocolMappers", []):
            if not isinstance(mapper_obj, dict) or not isinstance(
                mapper_obj.get("config", {}), dict
            ):
                self.errors = True
                emit(
                    "KC_PARSE",
                    "Mapper mal formé ; détails masqués.",
                    "protocolMappers",
                    severity="ERROR",
                )
        obj["protocolMappers"] = [
            m
            for m in obj.get("protocolMappers", [])
            if isinstance(m, dict) and isinstance(m.get("config", {}), dict)
        ]

        if full_realm:
            realm_rules(self, path, text, obj, start, emit, env)
        client_rules(self, path, text, obj, start, emit, env, inherited)
        secret_rules(self, path, text, obj, start, emit)

    @staticmethod
    def object_line(text, obj, start):
        value = obj.get("clientId", obj.get("realm"))
        if isinstance(value, str):
            normal = text.replace('\\"', '"')
            for n, line in enumerate(normal.splitlines(), 1):
                if n >= start and re.search(
                    r'"(?:clientId|realm)"\s*:\s*' + re.escape(json.dumps(value)), line
                ):
                    return n
        for key in ("user.attribute", "claim.name"):
            value = obj.get(key)
            if isinstance(value, str):
                for n, line in enumerate(text.replace('\\"', '"').splitlines(), 1):
                    if n >= start and re.search(
                        re.escape(json.dumps(key)) + r"\s*:\s*" + re.escape(json.dumps(value)), line
                    ):
                        return n
        return start
