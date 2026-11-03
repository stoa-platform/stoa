"""Offline tenant claim contracts: real exports and rendered bootstrap payloads."""

import json
import shlex
import unittest
from pathlib import Path

import yaml
from helm_contract_support import render
from keycloak_audit_lib.common import json_objects, walk

ROOT = Path(__file__).resolve().parents[2]
CLIENTS = ("control-plane-ui", "stoa-portal", "control-plane-api")
CONFIG = {
    "user.attribute": "tenant_id",
    "claim.name": "tenant_id",
    "jsonType.label": "String",
    "multivalued": "false",
    "id.token.claim": "true",
    "access.token.claim": "true",
    "userinfo.token.claim": "true",
}


class TenantClaimTests(unittest.TestCase):
    def realm_profile(self, realm):
        providers = realm.get("components", {}).get(
            "org.keycloak.userprofile.UserProfileProvider", []
        )
        self.assertEqual(len(providers), 1, "Realm must import one effective user profile")
        self.assertEqual(providers[0]["providerId"], "declarative-user-profile")
        configs = providers[0]["config"]["kc.user.profile.config"]
        self.assertEqual(len(configs), 1)
        return json.loads(configs[0])

    def assert_tenant_mapper(self, mappers):
        tenant = [m for m in mappers if m.get("config", {}).get("claim.name") == "tenant_id"]
        self.assertEqual(len(tenant), 1, "Exactly one effective tenant_id mapper is required")
        mapper = tenant[0]
        self.assertEqual(mapper["protocol"], "openid-connect")
        self.assertEqual(mapper["protocolMapper"], "oidc-usermodel-attribute-mapper")
        self.assertIs(mapper["consentRequired"], False)
        # Pin mapper options; inherited group attributes are blocked by separate guards.
        self.assertEqual(mapper["config"], CONFIG)

    def assert_admin_only_profile(self, profile):
        attributes = [a for a in profile["attributes"] if a["name"] == "tenant_id"]
        self.assertEqual(len(attributes), 1)
        self.assertEqual(attributes[0]["permissions"], {"view": ["admin"], "edit": ["admin"]})
        self.assertIs(attributes[0]["multivalued"], False)
        self.assertIn(profile.get("unmanagedAttributePolicy"), (None, "ADMIN_VIEW", "ADMIN_EDIT"))

    def assert_no_group_tenant_id(self, document):
        for node in walk(document):
            # Recognize user/client/realm payloads; unnamed group updates stay guarded.
            if not any(key in node for key in ("username", "clientId", "realm")) and isinstance(
                node.get("attributes"), dict
            ):
                self.assertNotIn(
                    "tenant_id", node["attributes"], "Groups must not assign tenant_id"
                )
            for key in ("groups", "subGroups"):
                for group in node.get(key, []):
                    if isinstance(group, dict):
                        self.assertNotIn(
                            "tenant_id",
                            group.get("attributes", {}),
                            "Groups must not assign tenant_id",
                        )

    def test_reviewed_mapper_pins_user_attribute_and_claim_outputs(self):
        mapper = json.loads((ROOT / "deploy/keycloak/tenant-id-mapper.json").read_text())
        self.assert_tenant_mapper([mapper])

    def test_realm_export_includes_claim_without_optional_scope_request(self):
        realm = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
        self.assertEqual(realm["realm"], "stoa")
        self.assert_no_group_tenant_id(realm)
        self.assert_admin_only_profile(self.realm_profile(realm))
        clients = {c["clientId"]: c for c in realm["clients"]}
        scopes = {s["name"]: s for s in realm["clientScopes"]}
        for client_id in CLIENTS:
            with self.subTest(client=client_id):
                client = clients[client_id]
                effective = list(client.get("protocolMappers", []))
                for name in client.get("defaultClientScopes", []):
                    effective.extend(scopes.get(name, {}).get("protocolMappers", []))
                self.assert_tenant_mapper(effective)

    def test_rendered_bootstrap_includes_claim_on_all_three_clients(self):
        result = render(
            "--set",
            "stoa.bootstrap.enabled=true",
            "--set",
            "stoa.bootstrap.keycloak.existingSecret=unit-bootstrap",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config_map = next(
            doc
            for doc in yaml.safe_load_all(result.stdout)
            if doc
            and doc.get("kind") == "ConfigMap"
            and doc["metadata"]["name"] == "stoa-bootstrap-script"
        )
        # Parse only; the shell script is never executed and no server is contacted.
        payloads = [
            obj
            for token in shlex.split(config_map["data"]["bootstrap.sh"], comments=True)
            for obj, _ in json_objects(token.replace("\\$", "$"))
        ]
        for payload in payloads:
            self.assert_no_group_tenant_id(payload)
        realms = [obj for obj in payloads if "realm" in obj]
        self.assertEqual(len(realms), 1, "Bootstrap must create the realm with its user profile")
        profile = self.realm_profile(realms[0])
        self.assert_admin_only_profile(profile)
        realm = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
        self.assertEqual(profile, self.realm_profile(realm))
        clients = {obj["clientId"]: obj for obj in payloads if obj.get("clientId") in CLIENTS}
        for client_id in CLIENTS:
            with self.subTest(client=client_id):
                self.assert_tenant_mapper(clients[client_id].get("protocolMappers", []))
        self.assertIs(clients["control-plane-api"]["bearerOnly"], True)

    def test_group_guard_rejects_direct_and_nested_assignments(self):
        group = {"name": "example", "attributes": {"tenant_id": []}}
        for document in (
            group,
            {"attributes": group["attributes"]},
            {"groups": [group]},
            {"groups": [{"subGroups": [group]}]},
            {"groups": [{**group, "username": "ignored"}]},
        ):
            with self.subTest(document=document), self.assertRaises(AssertionError):
                self.assert_no_group_tenant_id(document)
        self.assert_no_group_tenant_id(
            {"users": [{"username": "assigned", "attributes": group["attributes"]}]}
        )

    def test_profile_guard_rejects_self_service_permissions(self):
        for role in ("view", "edit"):
            attribute = {
                "name": "tenant_id",
                "permissions": {"view": ["admin"], "edit": ["admin"]},
                "multivalued": False,
            }
            attribute["permissions"][role].append("user")
            with self.subTest(role=role), self.assertRaises(AssertionError):
                self.assert_admin_only_profile({"attributes": [attribute]})

    def test_declarative_api_scope_includes_all_three_claim_outputs(self):
        path = ROOT / "deploy/platform-bootstrap/scopes/stoa-scopes.yaml"
        declaration = yaml.safe_load(path.read_text())
        scopes = declaration["spec"]["clientScopes"]
        api_scope = next(scope for scope in scopes if scope["name"] == "stoa-api")
        self.assert_tenant_mapper(api_scope["protocolMappers"])


if __name__ == "__main__":
    unittest.main()
