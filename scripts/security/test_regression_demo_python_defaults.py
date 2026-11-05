"""Inspect demo seeders without importing them or contacting any service."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DemoPythonDefaultsTests(unittest.TestCase):
    def test_targets_are_local_and_new_passwords_require_rotation(self):
        for name in ("seed-rpo-demo.py", "scenario-manager.py"):
            with self.subTest(script=name):
                tree = ast.parse((ROOT / "scripts/demo" / name).read_text())
                targets = {
                    node.targets[0].id: ast.literal_eval(node.value.args[1])
                    for node in tree.body
                    if isinstance(node, ast.Assign)
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in {"API_URL", "KEYCLOAK_URL"}
                }
                self.assertEqual(
                    targets,
                    {
                        "API_URL": "http://localhost:8000",
                        "KEYCLOAK_URL": "http://localhost:8080",
                    },
                )
                create_user = next(
                    node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "create_keycloak_user"
                )
                fields = {
                    key.value: value
                    for node in ast.walk(create_user) if isinstance(node, ast.Dict)
                    for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant)
                }
                self.assertIs(ast.literal_eval(fields["temporary"]), True)
                self.assertEqual(ast.literal_eval(fields["requiredActions"]), ["UPDATE_PASSWORD"])
