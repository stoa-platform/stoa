# SPDX-License-Identifier: Apache-2.0
"""CAB-2359: docs/platform-catalog.yaml is exempt from the changed-file image pinning gate.

The catalog is an inventory, not a deployment input. The skip is an exact-path
match in main(); findings() stays path-agnostic and every other path, including
lookalike catalog paths, is still scanned.
"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

script = Path(__file__).with_name("check_image_pinning.py")
if not script.exists():
    script = Path(__file__).parents[1] / "check_image_pinning.py"
spec = importlib.util.spec_from_file_location("guard", script)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
D = "sha256:" + "a" * 64
PINNED = "image" + ": nginx@" + D + "\n"
UNPINNED = "image" + ": nginx:1.2.3\n"
CATALOG = "docs/platform-catalog.yaml"


def guard_between(base_files, head_files):
    with tempfile.TemporaryDirectory() as root:
        def git(*args):
            return subprocess.check_output(["git", "-C", root, *args], stderr=subprocess.DEVNULL).decode().strip()

        def write(mapping):
            for path, text in mapping.items():
                target = Path(root) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)

        write(base_files)
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Guard", "-c", "user.email=guard@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        base = git("rev-parse", "HEAD")
        write(head_files)
        git("add", ".")
        git("-c", "user.name=Guard", "-c", "user.email=guard@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        head = git("rev-parse", "HEAD")
        return subprocess.run(
            ["python3", "-B", str(script.resolve()), "--base", base, "--head", head],
            cwd=root, capture_output=True, text=True,
        )


class CatalogExemptionRegressionTests(unittest.TestCase):
    def test_regression_cab_2359_catalog_only_diff_passes(self):
        self.assertEqual(guard.findings(CATALOG, UNPINNED), [(1, "image-unpinned")])
        result = guard_between({CATALOG: PINNED}, {CATALOG: UNPINNED})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_regression_cab_2359_catalog_plus_unpinned_chart_reports_chart_only(self):
        chart = "charts/stoa-platform/values.yaml"
        paths = (CATALOG, chart)
        result = guard_between({path: PINNED for path in paths}, {path: UNPINNED for path in paths})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, chart + ":1:image-unpinned\n", ""))

    def test_regression_cab_2359_catalog_lookalike_paths_stay_scanned(self):
        lookalikes = ("deploy/docs/platform-catalog.yaml", "docs/other/platform-catalog.yaml")
        paths = (CATALOG, *lookalikes)
        result = guard_between({path: PINNED for path in paths}, {path: UNPINNED for path in paths})
        expected = "".join(path + ":1:image-unpinned\n" for path in lookalikes)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, expected, ""))


if __name__ == "__main__":
    unittest.main()
