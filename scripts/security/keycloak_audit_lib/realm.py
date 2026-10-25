"""Realm admission, session and rotation rules."""

import re

from keycloak_audit_lib.common import BOUNDS, REQUIRED_TIMES, bounded


def realm_rules(self, path, text, obj, start, emit, env):
    for key in ("registrationAllowed", "resetPasswordAllowed"):
        if obj.get(key) is not False:
            emit(
                "KC_REGISTRATION" if key == "registrationAllowed" else "KC_RESET",
                "Fonction ouverte ou fermeture non explicite.",
                key,
            )
    policy = obj.get("passwordPolicy", "")
    minimum = 12 if env == "dev" else 16
    m = re.search(r"(?:^|\band\s+)length\((\d+)\)", str(policy))
    if (
        not m
        or int(m[1]) < minimum
        or not re.search(r"\bnotUsername(?:\(\))?(?:\s|$)", str(policy))
    ):
        emit(
            "KC_PASSWORD_POLICY",
            "Politique absente ou insuffisante pour cet environnement.",
            "passwordPolicy",
        )
    for key, maximum in BOUNDS.items():
        if key in obj or key in REQUIRED_TIMES:
            if not bounded(obj.get(key), maximum):
                emit(
                    "KC_LIFETIME",
                    "Durée absente, non positive, dynamique ou supérieure au plafond.",
                    key,
                )
    if obj.get("offlineSessionMaxLifespanEnabled") is not True:
        emit(
            "KC_OFFLINE_UNBOUNDED",
            "Plafond de session hors ligne non activé.",
            "offlineSessionMaxLifespanEnabled",
        )
    for idle, maximum in [
        ("ssoSessionIdleTimeout", "ssoSessionMaxLifespan"),
        ("clientSessionIdleTimeout", "clientSessionMaxLifespan"),
    ]:
        if all(isinstance(obj.get(k), int) for k in (idle, maximum)) and obj[idle] > obj[maximum]:
            emit("KC_SESSION_ORDER", "Inactivité supérieure à la durée maximale.", idle)
    if obj.get("revokeRefreshToken") is not True or obj.get("refreshTokenMaxReuse") != 0:
        emit(
            "KC_REFRESH_ROTATION",
            "Rotation stricte des refresh tokens non explicite.",
            "revokeRefreshToken",
            severity="MEDIUM",
        )
    if obj.get("sslRequired") != "all":
        emit(
            "KC_TLS",
            "Vérifier la terminaison TLS et les en-têtes de proxy.",
            "sslRequired",
            severity="REVIEW",
            dev_warning=True,
        )
    if obj.get("users"):
        emit(
            "KC_DEFAULT_USERS",
            "Utilisateurs importés ; identités et valeurs masquées.",
            "users",
            dev_warning=True,
        )
    scopes = {s.get("name"): s for s in obj.get("clientScopes", []) if isinstance(s, dict)}
    for c in obj.get("clients", []):
        if not isinstance(c, dict):
            continue
        cstart = self.object_line(text, c, start)
        self.representation(path, text, c, cstart, inherited=scopes)
    # Other nested objects (IdP credentials, tenant attributes) too.
