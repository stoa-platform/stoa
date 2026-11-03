"""Offline tenant claim contracts: real exports and rendered bootstrap payloads."""

import json
import unittest
from pathlib import Path

import yaml
from helm_contract_support import render
from keycloak_audit_lib.common import json_objects

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
    def assert_tenant_mapper(self, mappers):
        tenant = [m for m in mappers if m.get("config", {}).get("claim.name") == "tenant_id"]
        self.assertEqual(len(tenant), 1, "Exactly one effective tenant_id mapper is required")
        mapper = tenant[0]
        self.assertEqual(mapper["protocol"], "openid-connect")
        self.assertEqual(mapper["protocolMapper"], "oidc-usermodel-attribute-mapper")
        self.assertIs(mapper["consentRequired"], False)
        # Exact equality also excludes hardcoded values, defaults and group aggregation.
        self.assertEqual(mapper["config"], CONFIG)

    def test_reviewed_mapper_has_no_fallback(self):
        mapper = json.loads((ROOT / "deploy/keycloak/tenant-id-mapper.json").read_text())
        self.assert_tenant_mapper([mapper])

    def test_realm_export_includes_claim_without_optional_scope_request(self):
        realm = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
        self.assertEqual(realm["realm"], "stoa")
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
        clients = {
            obj["clientId"]: obj
            for obj, _ in json_objects(config_map["data"]["bootstrap.sh"])
            if obj.get("clientId") in CLIENTS
        }
        for client_id in CLIENTS:
            with self.subTest(client=client_id):
                self.assert_tenant_mapper(clients[client_id].get("protocolMappers", []))
        self.assertIs(clients["control-plane-api"]["bearerOnly"], True)

    def test_declarative_api_scope_includes_all_three_claim_outputs(self):
        path = ROOT / "deploy/platform-bootstrap/scopes/stoa-scopes.yaml"
        declaration = yaml.safe_load(path.read_text())
        scopes = declaration["spec"]["clientScopes"]
        api_scope = next(scope for scope in scopes if scope["name"] == "stoa-api")
        self.assert_tenant_mapper(api_scope["protocolMappers"])


if __name__ == "__main__":
    unittest.main()
