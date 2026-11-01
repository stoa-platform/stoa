# SPDX-License-Identifier: Apache-2.0
"""CAB-2343: generated Compose follows the canonical image producer."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class StoactlImagePinningRegressionTests(unittest.TestCase):
    def test_regression_template_uses_verified_canonical_producer_and_nginx(self):
        producer = (ROOT / ".github/workflows/stoa-gateway-ci.yml").read_text()
        image_name = re.search(r"(?m)^      image-name: ([a-z-]+)$", producer).group(1)
        template = (ROOT / "stoa-go/internal/cli/cmd/init/templates.go").read_text()
        compose = template.split("const dockerComposeTemplate = `", 1)[1].split("`", 1)[0]
        images = re.findall(r"(?m)^    image: (.+)$", compose)
        proof = json.loads((ROOT / "docs/audits/2026-11-01-cab2343-digest-pinning/stoactl-template-registry.json").read_text())
        expected = dict(zip(("gateway", "echo"), (f"ghcr.io/stoa-platform/{image_name}", "nginx"), strict=True))
        self.assertEqual(len(images), 2)
        for item, image in zip(proof["images"], images, strict=True):
            with self.subTest(role=item["role"]):
                self.assertEqual(item["digest"], item["header_digest"])
                self.assertEqual(item["digest"], item["body_sha256"])
                self.assertTrue(item["digest_get_verified"])
                self.assertEqual(image, expected[item["role"]] + "@" + item["digest"])
        self.assertEqual(compose.count("    pull_policy: missing"), 2)
