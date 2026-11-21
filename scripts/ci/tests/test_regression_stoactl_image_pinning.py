# SPDX-License-Identifier: Apache-2.0
"""Regression test: generated Compose follows the canonical image producer."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Registry-verified immutable digests (audit proof archived privately).
VERIFIED_STOACTL_DIGESTS = (
    ("gateway", "sha256:0ea4741d3b83c4de5f5f221a42969e4afbee17ed1d66d40fb92500d77dce991e"),
    ("echo", "sha256:785835ea65db4bba6f021acc0f3be91b0fef76a53fe41f8588c6698d2aed0606"),
)


class StoactlImagePinningRegressionTests(unittest.TestCase):
    def test_regression_template_uses_verified_canonical_producer_and_nginx(self):
        producer = (ROOT / ".github/workflows/stoa-gateway-ci.yml").read_text()
        image_name = re.search(r"(?m)^      image-name: ([a-z-]+)$", producer).group(1)
        template = (ROOT / "stoa-go/internal/cli/cmd/init/templates.go").read_text()
        compose = template.split("const dockerComposeTemplate = `", 1)[1].split("`", 1)[0]
        images = re.findall(r"(?m)^    image: (.+)$", compose)
        expected = dict(zip(("gateway", "echo"), (f"ghcr.io/stoa-platform/{image_name}", "nginx"), strict=True))
        self.assertEqual(len(images), 2)
        for (role, digest), image in zip(VERIFIED_STOACTL_DIGESTS, images, strict=True):
            with self.subTest(role=role):
                self.assertEqual(image, expected[role] + "@" + digest)
        self.assertEqual(compose.count("    pull_policy: missing"), 2)
