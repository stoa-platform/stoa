"""Synthetic representations and finding recorder for rule tests."""

from keycloak_audit_lib.common import Finding, environment


def safe_realm():
    return {
        "realm": "unit-test",
        "enabled": True,
        "sslRequired": "all",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "passwordPolicy": "length(16) and notUsername and maxLength(128)",
        "accessTokenLifespan": 300,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800,
        "offlineSessionIdleTimeout": 86400,
        "offlineSessionMaxLifespan": 604800,
        "offlineSessionMaxLifespanEnabled": True,
        "revokeRefreshToken": True,
        "refreshTokenMaxReuse": 0,
        "clients": [],
        "users": [],
    }


def safe_client():
    return {
        "clientId": "control-plane-ui",
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "implicitFlowEnabled": False,
        "redirectUris": ["https://console.example.test", "https://console.example.test/"],
        "webOrigins": ["https://console.example.test"],
        "attributes": {"pkce.code.challenge.method": "S256"},
        "protocolMappers": [
            {
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.client.audience": "control-plane-api",
                    "access.token.claim": "true",
                },
            },
            {
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {
                    "user.attribute": "tenant_id",
                    "claim.name": "tenant_id",
                    "access.token.claim": "true",
                },
            },
        ],
    }


class Recorder:
    def __init__(self, mode="auto"):
        self.mode = mode
        self.errors = False
        self.findings = []
        self.objects = []

    def add(self, path, text, rule, message, key="", start=1, severity="HIGH", dev_warning=False):
        env = environment(path, self.mode)
        if env == "dev" and dev_warning:
            severity = "WARN"
        self.findings.append(Finding(path, start, rule, severity, env, message))

    def representation(self, path, text, obj, start=1, **kwargs):
        self.objects.append(obj)

    @staticmethod
    def object_line(text, obj, start):
        return start


def rules(recorder):
    return {finding.rule for finding in recorder.findings}
