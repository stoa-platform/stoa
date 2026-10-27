"""Régressions hors ligne ; données synthétiques, aucun accès au clone nécessaire."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

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

    def test_secrets_and_users_detected_without_values(self):
        obj = safe_realm()
        marker = "SYNTHETIC_SENSITIVE_VALUE_8c7a"
        obj["clients"] = [dict(safe_client(), secret=marker)]
        obj["users"] = [
            {"username": "private-identity", "credentials": [{"type": "password", "value": marker}]}
        ]
        result = audit(obj)
        self.assertTrue(
            {"KC_DEFAULT_USERS", "KC_HARDCODED_SECRET", "KC_USER_PASSWORD"} <= rules(result)
        )
        output = json.dumps([kc.asdict(f) for f in result.findings])
        self.assertNotIn(marker, output)
        self.assertNotIn("private-identity", output)

    def test_placeholders_are_not_secrets(self):
        for value in ["${CLIENT_SECRET}", "REPLACE_FROM_VAULT", "<from-secret-store>"]:
            self.assertNotIn("KC_HARDCODED_SECRET", rules(audit(dict(safe_client(), secret=value))))

    def test_component_credentials_in_arrays_are_redacted(self):
        obj = safe_realm()
        obj["components"] = {"ldap": [{"config": {"bindCredential": ["SYNTHETIC_PRIVATE_MARKER"]}}]}
        result = audit(obj)
        self.assertIn("KC_HARDCODED_SECRET", rules(result))
        self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", str(result.findings))


class FormatTests(unittest.TestCase):
    def test_yaml_keycloak_admin_literal_is_redacted(self):
        marker = "_".join(["SYNTHETIC", "PRIVATE", "MARKER"])
        text = (
            "services:\n  keycloak:\n    environment:\n      KC_BOOTSTRAP_ADMIN_PASSWORD: "
            + marker
            + "\n"
        )
        result = run_text(text, "deploy/unit.yaml")
        self.assertIn("KC_HARDCODED_SECRET", rules(result))
        self.assertNotIn(marker, str(result.findings))

    def test_dcr_session_and_token_bounds(self):
        text = 'kind: Application\nspec:\n  tokenLifespans:\n    idToken: 3600\n  keycloakAttributes:\n    client.session.max.lifespan: "86400"\n'
        self.assertTrue(
            {"KC_DECLARED_LIFETIME", "KC_CLIENT_LIFETIME"}
            <= rules(run_text(text, "deploy/unit.yaml"))
        )

    def test_malformed_client_collections_fail_closed(self):
        for key, value in [
            ("protocolMappers", "invalid"),
            ("defaultClientScopes", True),
            ("grantTypes", 42),
        ]:
            obj = safe_client()
            obj[key] = value
            result = audit(obj)
            self.assertTrue(result.errors)
            self.assertIn("KC_PARSE", rules(result))

    def test_unrelated_command_substitution_is_not_secret_output(self):
        text = 'keycloak=yes\nENCODED=$(echo -n "$CLIENT_SECRET" | base64)\n'
        self.assertNotIn("KC_SECRET_OUTPUT", rules(run_text(text, "scripts/unit.sh")))

    def test_shell_heredoc_and_escaped_helm_payloads(self):
        payload = json.dumps(dict(safe_client(), directAccessGrantsEnabled=True), indent=2)
        for text, path in [
            ("CONFIG=$(cat <<EOF\n" + payload + "\nEOF\n)", "scripts/setup-test.sh"),
            (
                'data:\n  bootstrap.sh: |\n    curl -d "' + payload.replace('"', '\\"') + '"',
                "charts/x/templates/bootstrap-job.yaml",
            ),
        ]:
            with self.subTest(path=path):
                self.assertIn("KC_DIRECT_GRANT", rules(run_text(text, path)))

    def test_kcadm_continuations_and_quoted_attributes(self):
        text = """#!/bin/bash
keycloak=/unused
$KCADM create clients -r example \\
  -s clientId=unit-client \\
  -s publicClient=true \\
  -s directAccessGrantsEnabled=true \\
  -s 'redirectUris=["https://unit.example/*"]' \\
  -s 'attributes={"pkce.code.challenge.method":"S256"}'
"""
        found = rules(run_text(text, "scripts/unit.sh"))
        self.assertTrue({"KC_DIRECT_GRANT", "KC_REDIRECT_WILDCARD"} <= found)
        self.assertNotIn("KC_PKCE", found)

    def test_multidocument_yaml_nested_realm(self):
        text = "kind: KeycloakRealmImport\nspec:\n  realm:\n" + "\n".join(
            "    " + line for line in kc.yaml.safe_dump(safe_realm()).splitlines()
        )
        text += "\n---\n" + kc.yaml.safe_dump(dict(safe_client(), implicitFlowEnabled=True))
        self.assertIn("KC_IMPLICIT", rules(run_text(text, "deploy/unit.yaml")))

    def test_line_numbers_discriminate_clients(self):
        obj = safe_realm()
        obj["clients"] = [
            safe_client(),
            dict(safe_client(), clientId="second", implicitFlowEnabled=True),
        ]
        text = json.dumps(obj, indent=2)
        result = run_text(text, "deploy/unit.json")
        finding = next(f for f in result.findings if f.rule == "KC_IMPLICIT")
        self.assertIn("implicitFlowEnabled", text.splitlines()[finding.line - 1])
        self.assertIn("true", text.splitlines()[finding.line - 1])

    def test_malformed_json_does_not_leak_parser_context(self):
        result = run_text('{"secret": "SENSITIVE_SENTINEL", INVALID}', "deploy/unit.json")
        self.assertTrue(result.errors)
        self.assertIn("KC_PARSE", rules(result))
        self.assertNotIn("SENSITIVE_SENTINEL", str(result.findings))

    def test_static_analysis_does_not_execute_shell_or_python(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            marker = Path(temp) / "must-not-exist"
            text = f"keycloak=yes\n$(touch {marker})\n$KCADM update realms/x -s registrationAllowed=true\n"
            self.assertIn("KC_REGISTRATION", rules(run_text(text, "scripts/unit.sh")))
            self.assertFalse(marker.exists())

    def test_environment_override_does_not_silently_whitelist_dev(self):
        self.assertEqual("prod", kc.environment("scripts/new-bootstrap.sh"))
        self.assertEqual("dev", kc.environment("deploy/docker-compose/init/realm.json"))
        self.assertEqual("prod", kc.environment("deploy/docker-compose/init/realm.json", "prod"))

    def test_symlinks_credentials_and_encrypted_files_are_not_read(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            (root / "realm.json").write_text(json.dumps(safe_realm()))
            (root / "credentials.json").write_text("{this would cause a parse error")
            (root / "opaque.md").write_bytes(b"\x00GITCRYPT\xff")
            (root / "link").symlink_to("/does-not-exist", target_is_directory=True)
            result = kc.Audit().scan(root)
            self.assertFalse(result.errors)
            statuses = {x["status"] for x in result.inventory}
            self.assertIn("credential-path-not-read", statuses)
            self.assertIn("encrypted-not-decrypted", statuses)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            p = root / "realm.json"
            with contextlib.redirect_stdout(io.StringIO()):
                p.write_text(json.dumps(safe_realm()))
                self.assertEqual(0, kc.main([str(root)]))
                p.write_text(json.dumps(dict(safe_realm(), registrationAllowed=True)))
                self.assertEqual(1, kc.main([str(root)]))
                p.write_text('{"realm": INVALID}')
                self.assertEqual(2, kc.main([str(root)]))


if __name__ == "__main__":
    unittest.main()
