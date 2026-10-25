"""Régressions hors ligne ; données synthétiques, aucun accès au clone nécessaire."""

import json
import unittest

import keycloak_audit as kc


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


def audit(obj, path="deploy/keycloak/test.json", mode="auto"):
    return run_text(json.dumps(obj, indent=2), path, mode)


def run_text(text, path, mode="auto"):
    result = kc.Audit(mode)
    result.audit_text(path, text)
    return result


def rules(result):
    return {f.rule for f in result.findings}


class PolicyTests(unittest.TestCase):
    def test_closed_realm_passes(self):
        self.assertEqual([], audit(safe_realm()).findings)

    def test_registration_and_reset_are_explicitly_closed(self):
        for field, rule in [
            ("registrationAllowed", "KC_REGISTRATION"),
            ("resetPasswordAllowed", "KC_RESET"),
        ]:
            for value in [True, None, "false"]:
                with self.subTest(field=field, value=value):
                    obj = safe_realm()
                    if value is None:
                        del obj[field]
                    else:
                        obj[field] = value
                    self.assertIn(rule, rules(audit(obj)))

    def test_password_policy_environments(self):
        obj = safe_realm()
        obj["passwordPolicy"] = "length(12) and notUsername"
        self.assertIn("KC_PASSWORD_POLICY", rules(audit(obj)))
        self.assertNotIn(
            "KC_PASSWORD_POLICY", rules(audit(obj, "deploy/docker-compose/init/test.json"))
        )
        for policy in [
            "",
            "length(1) and notUsername",
            "length(16)",
            "maxLength(128) and notUsername",
        ]:
            obj["passwordPolicy"] = policy
            self.assertIn("KC_PASSWORD_POLICY", rules(audit(obj)))

    def test_all_lifetimes_reject_zero_negative_boolean_dynamic_and_excess(self):
        for key, maximum in kc.BOUNDS.items():
            for value in [0, -1, True, "${DYNAMIC}", maximum + 1]:
                with self.subTest(key=key, value=value):
                    obj = safe_realm()
                    obj[key] = value
                    self.assertIn("KC_LIFETIME", rules(audit(obj)))

    def test_offline_max_requires_enabled_flag(self):
        obj = safe_realm()
        obj["offlineSessionMaxLifespanEnabled"] = False
        self.assertIn("KC_OFFLINE_UNBOUNDED", rules(audit(obj)))

    def test_refresh_rotation(self):
        obj = safe_realm()
        obj["refreshTokenMaxReuse"] = 1
        self.assertIn("KC_REFRESH_ROTATION", rules(audit(obj)))

    def test_session_order(self):
        obj = safe_realm()
        obj["ssoSessionMaxLifespan"] = 600
        self.assertIn("KC_SESSION_ORDER", rules(audit(obj)))

    def test_safe_client_passes(self):
        self.assertEqual([], audit(safe_client()).findings)

    def test_grants(self):
        for key, rule in [
            ("directAccessGrantsEnabled", "KC_DIRECT_GRANT"),
            ("implicitFlowEnabled", "KC_IMPLICIT"),
        ]:
            obj = safe_client()
            obj[key] = True
            self.assertIn(rule, rules(audit(obj)))

    def test_public_pkce_missing_plain_and_s256(self):
        for value in [None, "plain", "S256"]:
            obj = safe_client()
            obj["attributes"] = {} if value is None else {"pkce.code.challenge.method": value}
            self.assertEqual(value != "S256", "KC_PKCE" in rules(audit(obj)))

    def test_device_only_public_client_does_not_require_redirect_pkce(self):
        obj = safe_client()
        obj.update(clientId="device-cli", standardFlowEnabled=False, redirectUris=[], attributes={})
        self.assertNotIn("KC_PKCE", rules(audit(obj)))

    def test_saml_is_not_oidc(self):
        obj = safe_client()
        obj.update(protocol="saml", attributes={})
        self.assertNotIn("KC_PKCE", rules(audit(obj)))

    def test_wildcard_and_http_loopback_in_prod(self):
        obj = safe_client()
        obj["redirectUris"] = ["*", "http://localhost:3000/*"]
        self.assertTrue(
            {"KC_REDIRECT_WILDCARD", "KC_REDIRECT_HTTP", "KC_PROD_LOOPBACK"} <= rules(audit(obj))
        )

    def test_client_override_lifespan(self):
        obj = safe_client()
        obj["attributes"]["access.token.lifespan"] = "3600"
        self.assertIn("KC_CLIENT_LIFETIME", rules(audit(obj)))

    def test_default_scope_mappers_count_optional_do_not(self):
        obj = safe_realm()
        client = safe_client()
        mappers = client.pop("protocolMappers")
        obj["clientScopes"] = [{"name": "stoa-api", "protocolMappers": mappers}]
        obj["clients"] = [client]
        client["defaultClientScopes"] = ["stoa-api"]
        self.assertFalse({"KC_AUDIENCE", "KC_TENANT_MISSING"} & rules(audit(obj)))
        client["defaultClientScopes"] = []
        client["optionalClientScopes"] = ["stoa-api"]
        self.assertTrue({"KC_AUDIENCE", "KC_TENANT_MISSING"} <= rules(audit(obj)))

    def test_audience_must_be_in_access_token(self):
        obj = safe_client()
        obj["protocolMappers"][0]["config"]["access.token.claim"] = "false"
        self.assertIn("KC_AUDIENCE", rules(audit(obj)))

    def test_tenant_attribute_mismatch(self):
        obj = safe_client()
        obj["protocolMappers"][1]["config"]["user.attribute"] = "tenant"
        self.assertIn("KC_TENANT_ATTRIBUTE", rules(audit(obj)))

    def test_hardcoded_tenant_requires_trust_review(self):
        obj = safe_client()
        obj["protocolMappers"][1]["config"]["claim.value"] = "${TENANT}"
        self.assertIn("KC_TENANT_TRUST", rules(audit(obj)))
