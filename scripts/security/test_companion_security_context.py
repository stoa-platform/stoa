"""Security contracts for the rendered STOA gateway companion container."""

import unittest

import yaml
from helm_contract_support import render


# Synthetic digests exercise rendering only; they are never deployed.
MAIN_DIGEST = "sha256:" + "a" * 64
SIDECAR_DIGEST = "sha256:" + "b" * 64
IMAGE_ARGUMENTS = (
    "--set", "stoaSidecar.mainGateway.image.repository=example.invalid/gateway",
    "--set", f"stoaSidecar.mainGateway.image.digest={MAIN_DIGEST}",
    "--set", f"stoaSidecar.image.digest={SIDECAR_DIGEST}",
)


class CompanionSecurityContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = render(
            "--set", "stoaSidecar.enabled=true",
            "--set", "stoaSidecar.mainGateway.enabled=true",
            *IMAGE_ARGUMENTS,
            "--show-only", "templates/stoa-sidecar-deployment.yaml",
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        deployments = [
            doc for doc in yaml.safe_load_all(result.stdout)
            if doc and doc.get("kind") == "Deployment"
        ]
        if len(deployments) != 1:
            raise AssertionError("Expected exactly one companion deployment")
        cls.pod = deployments[0]["spec"]["template"]["spec"]
        cls.companion = next(
            container for container in cls.pod["containers"]
            if container["name"] == "stoa-sidecar"
        )

    def test_images_use_the_supplied_digests(self):
        images = {container["name"]: container["image"] for container in self.pod["containers"]}
        self.assertEqual(images["webmethods"], f"example.invalid/gateway@{MAIN_DIGEST}")
        self.assertEqual(
            images["stoa-sidecar"], f"ghcr.io/stoa-platform/stoa-gateway@{SIDECAR_DIGEST}"
        )
        for container in self.pod["containers"]:
            self.assertEqual(container["imagePullPolicy"], "IfNotPresent")

    def test_non_root_identity(self):
        context = self.companion["securityContext"]
        self.assertIs(context["runAsNonRoot"], True)
        self.assertEqual(context.get("runAsUser"), 1000)
        self.assertEqual(context.get("runAsGroup"), 1000)

    def test_read_only_root_filesystem(self):
        self.assertIs(
            self.companion["securityContext"].get("readOnlyRootFilesystem"), True
        )

    def test_no_privilege_escalation_or_capabilities(self):
        context = self.companion["securityContext"]
        self.assertIs(context["privileged"], False)
        self.assertIs(context["allowPrivilegeEscalation"], False)
        self.assertEqual(context["capabilities"]["drop"], ["ALL"])
        self.assertFalse(context["capabilities"].get("add"))

    def test_runtime_default_seccomp(self):
        self.assertEqual(
            self.companion["securityContext"]["seccompProfile"],
            {"type": "RuntimeDefault"},
        )

    def test_temporary_files_use_a_writable_volume(self):
        mount = next(
            mount for mount in self.companion["volumeMounts"]
            if mount["mountPath"] == "/tmp"
        )
        self.assertFalse(mount.get("readOnly", False))
        volume = next(
            volume for volume in self.pod["volumes"]
            if volume["name"] == mount["name"]
        )
        self.assertEqual(volume["emptyDir"], {})


class CompanionImagePinningTests(unittest.TestCase):
    def test_enabling_without_a_main_gateway_repository_fails_closed(self):
        result = render("--set", "stoaSidecar.enabled=true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image repository is required", result.stderr)

    def test_missing_repositories_fail_closed(self):
        for field in ("stoaSidecar.mainGateway.image.repository", "stoaSidecar.image.repository"):
            with self.subTest(field=field):
                result = render(
                    "--set", "stoaSidecar.enabled=true", *IMAGE_ARGUMENTS,
                    "--set-string", f"{field}=",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("image repository is required", result.stderr)

    def test_invalid_or_missing_digests_fail_closed(self):
        for field in ("stoaSidecar.mainGateway.image.digest", "stoaSidecar.image.digest"):
            for digest in ("", "latest", "sha256:abc", "sha256:" + "g" * 64):
                with self.subTest(field=field, digest=digest):
                    result = render(
                        "--set", "stoaSidecar.enabled=true", *IMAGE_ARGUMENTS,
                        "--set-string", f"{field}={digest}",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("image digest", result.stderr)


if __name__ == "__main__":
    unittest.main()
