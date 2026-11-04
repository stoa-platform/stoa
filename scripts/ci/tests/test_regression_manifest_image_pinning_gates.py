# SPDX-License-Identifier: Apache-2.0
"""CAB-2343: manifest-only edits keep code gates and live E2E scoped."""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / ".claude/hooks/pre-push-quality-gate.sh"
WORKFLOW = ROOT / ".github/workflows/e2e-tests.yml"
FLAGS = ("HAS_PYTHON_API", "HAS_CONSOLE", "HAS_PORTAL", "HAS_GATEWAY", "HAS_E2E", "ONLY_DOCS")
COMPONENTS = (("control-plane-ui", "HAS_CONSOLE"), ("portal", "HAS_PORTAL"), ("stoa-gateway", "HAS_GATEWAY"))


def classified(paths):
    # Run the real classification block only: no hook, git, checks, or network.
    source = HOOK.read_text()
    start = source.index("HAS_PYTHON_API=false")
    end = source.index('done <<< "$CHANGED_FILES"', start) + len('done <<< "$CHANGED_FILES"')
    command = source[start:end] + '\nprintf "%s\\n" ' + " ".join('"$' + flag + '"' for flag in FLAGS)
    proc = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=True,
                          env={**os.environ, "CHANGED_FILES": "\n".join(paths)})
    return dict(zip(FLAGS, proc.stdout.splitlines(), strict=True))


class ManifestImagePinningGateRegressionTests(unittest.TestCase):
    def test_regression_manifests_skip_only_component_code_checks(self):
        for component, flag in COMPONENTS:
            with self.subTest(component=component):
                flags = classified([f"{component}/k8s/deployment.yaml"])
                self.assertEqual(flags[flag], "false")
                self.assertEqual(flags["ONLY_DOCS"], "false")  # OpSec/Council remain.

    def test_regression_source_and_mixed_changes_keep_code_checks(self):
        for component, flag in COMPONENTS:
            with self.subTest(component=component):
                source = f"{component}/src/main.rs"
                self.assertEqual(classified([source])[flag], "true")
                self.assertEqual(classified([f"{component}/k8s/deployment.yaml", source])[flag], "true")

    def test_regression_only_exact_gateway_e2e_compose_skips_rust(self):
        compose = "stoa-gateway/tests/e2e/docker-compose-test.yml"
        flags = classified([compose])
        self.assertEqual(flags["HAS_GATEWAY"], "false")
        self.assertEqual(flags["ONLY_DOCS"], "false")
        for adjacent in ("run-e2e.sh", "local_mcp_sdk_smoke.py", "another-compose.yml", "runtime_test.rs"):
            source = "stoa-gateway/tests/e2e/" + adjacent
            with self.subTest(source=source):
                self.assertEqual(classified([source])["HAS_GATEWAY"], "true")
                self.assertEqual(classified([compose, source])["HAS_GATEWAY"], "true")
        self.assertEqual(classified([compose, "stoa-gateway/src/main.rs"])["HAS_GATEWAY"], "true")

    def test_regression_gateway_e2e_compose_matches_verified_peer_images(self):
        source = (ROOT / "stoa-gateway/tests/e2e/docker-compose-test.yml").read_text()
        images = re.findall(r"(?m)^    image: (.+)$", source)
        proof = json.loads((ROOT / "docs/audits/2026-11-01-cab2343-digest-pinning/gateway-local-e2e-registry.json").read_text())
        self.assertEqual(len(images), 3)
        self.assertEqual(len(proof["images"]), 3)
        for entry, reference in zip(proof["images"], images, strict=True):
            self.assertTrue(entry["verified"])
            self.assertEqual(reference, entry["immutable"])
            self.assertTrue(reference.endswith("@" + entry["digest"]))
        self.assertEqual(source.count("    pull_policy: missing"), 3)

    def test_regression_api_and_e2e_checks_remain_enabled(self):
        flags = classified(["control-plane-api/src/main.py", "e2e/features/smoke.feature"])
        self.assertEqual(flags["HAS_PYTHON_API"], "true")
        self.assertEqual(flags["HAS_E2E"], "true")

    def test_regression_runtime_detector_uses_actual_push_diff(self):
        cases = [
            (["control-plane-ui/k8s/deployment.yaml"], "false"),
            (["portal/k8s/nested/deployment.yaml"], "false"),
            ([".github/workflows/e2e-tests.yml"], "false"),
            ([".github/scripts/e2e-runtime-changes.sh"], "false"),
            (["control-plane-ui/README.md", "e2e/docs/guide.md", "portal/README.md"], "false"),
            (["control-plane-ui/src/App.tsx"], "true"),
            (["portal/src/App.tsx"], "true"),
            (["e2e/features/smoke.feature"], "true"),
            (["control-plane-ui/k8s/deployment.yaml", "portal/src/App.tsx"], "true"),
            (["portal/k8s/deployment.yaml", "e2e/features/smoke.feature"], "true"),
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def git(*args, root=root):
                    return subprocess.run(["git", *args], cwd=root, text=True,
                                          capture_output=True, check=True).stdout.strip()
                git("init", "-q")
                git("config", "user.email", "test@example.invalid")
                git("config", "user.name", "Regression Test")
                (root / "seed").write_text("base")
                git("add", ".")
                git("commit", "-qm", "base")
                base = git("rev-parse", "HEAD")
                for name in paths:
                    p = root / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("changed")
                git("add", ".")
                git("commit", "-qm", "change")
                output = root / "output"
                proc = subprocess.run(["bash", str(ROOT / ".github/scripts/e2e-runtime-changes.sh"),
                                       base, git("rev-parse", "HEAD")], cwd=root, text=True,
                                      capture_output=True, check=True,
                                      env={**os.environ, "GITHUB_OUTPUT": str(output)})
                self.assertEqual(proc.stdout.strip(), f"runtime={expected}")
                self.assertEqual(output.read_text().strip(), f"runtime={expected}")

    def test_regression_schedule_manual_self_trigger_and_detector_wiring(self):
        source = WORKFLOW.read_text()
        push = source.split("\n  push:\n", 1)[1].split("\n  # Run daily", 1)[0]
        self.assertIn("- '.github/workflows/e2e-tests.yml'", push)
        self.assertIn("- '!control-plane-ui/k8s/**'", push)
        self.assertIn("- '!portal/k8s/**'", push)
        self.assertIn("\n  schedule:\n", source)
        self.assertIn("\n  workflow_dispatch:\n", source)
        changes = source.split("\n  changes:\n", 1)[1].split("\n  e2e-tests:\n", 1)[0]
        self.assertIn("if: github.event_name == 'push'", changes)
        self.assertIn('bash .github/scripts/e2e-runtime-changes.sh "$BASE_SHA" "$HEAD_SHA"', changes)
        job = source.split("\n  e2e-tests:\n", 1)[1].split("\n    permissions:", 1)[0]
        self.assertIn("needs: changes", job)
        self.assertIn("if: always() && (github.event_name != 'push' || "
                      "needs.changes.outputs.runtime == 'true')", job)

    def test_regression_live_e2e_never_runs_on_pull_requests(self):
        # The live suite drives the deployed environment, so a pull request run
        # cannot validate the PR. UI-only PRs rely on the mocked gates instead.
        triggers = WORKFLOW.read_text().split("\non:\n", 1)[1].split("\nconcurrency:\n", 1)[0]
        self.assertEqual(re.findall(r"(?m)^  ([a-z_]+):", triggers),
                         ["push", "schedule", "workflow_dispatch"])
        self.assertNotRegex(triggers, r"(?m)^\s*pull_request(_target)?:")
