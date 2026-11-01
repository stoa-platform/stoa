# SPDX-License-Identifier: Apache-2.0
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("guard", Path(__file__).parents[1] / "check_image_pinning.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ImageContextRegressionTests(unittest.TestCase):
    def test_regression_mixed_guide_keeps_real_image_findings(self):
        source = "\n".join([
            "See `src/module.py:123`.", "```sql", "SELECT name", "FROM entries", "```",
            "```dockerfile", "FROM nginx:1", "```", "docker" + " run alpine:3.20",
        ])
        self.assertEqual(guard.findings("docs/guide.md", source), [
            (7, "image-unpinned"), (9, "image-unpinned"),
        ])
