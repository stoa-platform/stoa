"""No preconfigured credentials in the local realm import."""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class CredentialTests(unittest.TestCase):
    def test_compose_client_secrets_are_required_environment_inputs(self):
        realm = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
        compose = yaml.safe_load((ROOT / "deploy/docker-compose/docker-compose.yml").read_text())
        environment = compose["services"]["keycloak"]["environment"]
        for client in realm["clients"]:
            if "secret" in client:
                name = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", client["secret"]).group(1)
                self.assertTrue(environment[name].startswith("${" + name + ":?"))
        example = (ROOT / "deploy/docker-compose/.env.example").read_text()
        for line in example.splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if "PASSWORD" in key or "SECRET" in key:
                    self.assertEqual("", value, key)

    def test_import_origins_are_unique_and_totp_registration_is_closed(self):
        realm = json.loads((ROOT / "deploy/docker-compose/init/keycloak-realm.json").read_text())
        for client in realm["clients"]:
            for key in ("redirectUris", "webOrigins"):
                entries = client.get(key, [])
                self.assertEqual(len(entries), len(set(entries)))
        totp = json.loads((ROOT / "deploy/keycloak/stoa-realm-totp.json").read_text())
        self.assertIs(False, totp["registrationAllowed"])
        source = (
            ROOT / "deploy/platform-bootstrap/applications/dcr-service-account-template.yaml"
        ).read_text()
        self.assertNotIn("28800  # 24 hours", source)
        self.assertNotIn("300  # 1 hour", source)
