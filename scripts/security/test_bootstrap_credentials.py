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
