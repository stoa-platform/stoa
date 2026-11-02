# SPDX-License-Identifier: Apache-2.0
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("guard", Path(__file__).parents[1] / "check_image_pinning.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ImageContextRegressionTests(unittest.TestCase):
    def build_workflow(self, image="ghcr.io/team/app@${{ steps.build.outputs.digest }}"):
        return "\n".join([
            "name: Build", "jobs:", "  publish:", "    runs-on: ubuntu-latest",
            "    steps:", "      - id: build",
            "        uses: docker/build-push-action@" + "a" * 40,
            "        with:", "          push: true",
            "      - name: Generate SBOM",
            "        uses: anchore/sbom-action@" + "b" * 40,
            "        with:", "          " + "image: " + image,
        ])

    def test_regression_sbom_accepts_pinned_prior_build_digest(self):
        for image in ("ghcr.io/team/app@${{ steps.build.outputs.digest }}",
                      "${{ env.IMAGE_PREFIX }}/${{ matrix.service }}@${{ steps.build.outputs.digest }}"):
            with self.subTest(image=image):
                self.assertFalse(guard.findings(".github/workflows/build.yml", self.build_workflow(image)))

    def test_regression_sbom_rejects_untrusted_digest_sources(self):
        source = self.build_workflow()
        cases = {
            "unpinned producer": source.replace("docker/build-push-action@" + "a" * 40, "docker/build-push-action@v7"),
            "unpinned consumer": source.replace("anchore/sbom-action@" + "b" * 40, "anchore/sbom-action@v0"),
            "other consumer": source.replace("anchore/sbom-action", "other/action"),
            "run producer": source.replace("uses: docker/build-push-action@" + "a" * 40, "run: echo digest=anything >> $GITHUB_OUTPUT"),
            "not pushed": source.replace("push: true", "push: false"),
            "missing push": source.replace("          push: true\n", ""),
            "environment digest": source.replace("steps.build.outputs.digest", "env.DIGEST"),
            "other output": source.replace("outputs.digest", "outputs.image"),
            "suffix": source + "-suffix",
            "fallback": source.replace("outputs.digest }}", "outputs.digest || 'latest' }}"),
            "other job": source.replace("      - name: Generate SBOM", "  scan:\n    steps:\n      - name: Generate SBOM"),
            "duplicate id": source.replace("      - name: Generate SBOM", "      - id: build\n        run: echo digest=anything\n      - name: Generate SBOM"),
            "nested env": source.replace("        with:\n          " + "image:", "        env:\n          " + "image:"),
        }
        producer = source[source.index("      - id: build"):source.index("      - name: Generate SBOM")]
        consumer = source[source.index("      - name: Generate SBOM"):]
        cases["future producer"] = source[:source.index("      - id: build")] + consumer + "\n" + producer
        for name, candidate in cases.items():
            with self.subTest(name=name):
                self.assertTrue(guard.findings(".github/workflows/build.yml", candidate))
        for path in ("config.yml", "docs/workflow.yml"):
            with self.subTest(path=path):
                self.assertTrue(guard.findings(path, source))

    def test_regression_mixed_guide_keeps_real_image_findings(self):
        source = "\n".join([
            "See `src/module.py:123`.", "```sql", "SELECT name", "FROM entries", "```",
            "```dockerfile", "FROM nginx:1", "```", "docker" + " run alpine:3.20",
        ])
        self.assertEqual(guard.findings("docs/guide.md", source), [
            (7, "image-unpinned"), (9, "image-unpinned"),
        ])
