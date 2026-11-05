"""Render contracts for immutable images in optional platform jobs."""

import re
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "security"))
from helm_contract_support import render


class ManifestImagePinningTests(unittest.TestCase):
    def test_optional_jobs_render_only_immutable_images(self):
        result = render(
            "--set", "gatewaySync.enabled=true",
            "--set", "vault.credentialsCheck.enabled=true",
            "--set", "stoa.bootstrap.firstAdmin.enabled=true",
            "--set", "stoa.bootstrap.firstAdmin.existingSecret=bootstrap-input",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        names = set()
        for obj in yaml.safe_load_all(result.stdout):
            if not obj or obj["kind"] not in {"Job", "CronJob", "Pod"}:
                continue
            names.add(obj["metadata"]["name"])
            spec = obj["spec"]
            if obj["kind"] == "CronJob":
                spec = spec["jobTemplate"]["spec"]
            if obj["kind"] != "Pod":
                spec = spec["template"]["spec"]
            for container in spec["containers"]:
                self.assertRegex(container["image"], r"^[^@\s]+@sha256:[0-9a-f]{64}$")
        self.assertTrue({"gateway-openapi-sync", "gateway-openapi-sync-manual",
                         "vault-db-credentials-check", "stoa-first-admin"} <= names)

    def test_optional_jobs_reject_unpinned_overrides(self):
        cases = (
            ("gatewaySync", "gatewaySync", ()),
            ("vault.credentialsCheck", "vault.credentialsCheck", ()),
            ("stoa.bootstrap.firstAdmin", "stoa.bootstrap.firstAdmin",
             ("--set", "stoa.bootstrap.firstAdmin.existingSecret=bootstrap-input")),
        )
        for enabled, image, extra in cases:
            for reference in ("", "example:latest", "example@sha256:invalid"):
                with self.subTest(image=image, reference=reference):
                    result = render("--set", f"{enabled}.enabled=true", *extra,
                                    "--set-string", f"{image}.image={reference}")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("image reference", result.stderr)

    def test_scalar_digest_override_is_preserved(self):
        reference = "registry.example/custom-curl@sha256:" + "a" * 64
        result = render("--set", "gatewaySync.enabled=true", "--set-string",
                        f"gatewaySync.image={reference}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(re.findall(re.escape(reference), result.stdout)), 2)


if __name__ == "__main__":
    unittest.main()
