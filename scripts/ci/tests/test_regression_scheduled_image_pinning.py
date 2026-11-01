# SPDX-License-Identifier: Apache-2.0
"""CAB-2343: scheduled scans must never fall back to a floating image."""
import os
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/security-scheduled.yml"


class ScheduledImagePinningRegressionTests(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text()
        self.scan = self.source.split("\n  gitleaks-full:", 1)[0]
        self.entries = dict(re.findall(
            r"^\s+- image_name: ([a-z0-9-]+)\n\s+image_ref: '([^']*)'",
            self.scan, re.MULTILINE,
        ))

    def test_regression_preserves_all_scan_targets_without_aliases(self):
        self.assertEqual(set(self.entries), {
            "control-plane-api", "control-plane-ui", "stoa-portal", "stoa-gateway",
        })
        for name, reference in self.entries.items():
            if not reference:
                self.assertEqual(name, "stoa-portal", "only the unproven package may stay unresolved")
            else:
                self.assertRegex(reference, rf"^ghcr\.io/stoa-platform/{name}@sha256:[0-9a-f]{{64}}$")
        self.assertIn("unresolved_repository: ghcr.io/stoa-platform/stoa-portal", self.scan)
        self.assertEqual(self.scan.count("image-ref: '${{ matrix.image_ref }}'"), 2)
        self.assertNotIn(":latest", self.scan)
        actions = re.findall(r"uses: aquasecurity/trivy-action@(\S+)", self.scan)
        self.assertEqual(len(actions), 2)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", action) for action in actions))

    def test_regression_scan_gate_rejects_missing_or_floating_references(self):
        step = re.search(
            r"      - name: Require verified immutable scan reference\n(.*?)(?=\n      - name:)",
            self.scan, re.DOTALL,
        )
        self.assertIsNotNone(step, "reference validation must precede scanner steps")
        block = step.group(1)
        self.assertNotIn("continue-on-error:", block)
        self.assertLess(step.start(), self.scan.index("uses: aquasecurity/trivy-action@"))
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        cases = [(ref, 0) for ref in self.entries.values() if ref]
        cases.extend([("", 1),
                      ("ghcr.io/stoa-platform/control-plane-api" + ":latest", 1)])
        for reference, expected in cases:
            with self.subTest(reference=reference):
                result = subprocess.run(
                    ["bash", "-e", "-c", script], capture_output=True, text=True,
                    env={**os.environ, "IMAGE_NAME": "scan-target", "IMAGE_REF": reference},
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected:
                    self.assertIn("::error::", result.stdout)


if __name__ == "__main__":
    unittest.main()
