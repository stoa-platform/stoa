"""Combined render of #3130 and #3131 compared with main.

Baseline is origin/main 9199b3442fb8ffdb387c5cfc0934e88e867afe0f, rendered with
``helm template <chart> <chart> --namespace stoa-system`` and the values files
shipped in the repo. Helm 3.14 (CI) and 3.16 produce the same normalized text.

``stoa-internal-keys`` data is generated with ``randAlphaNum`` whenever
``lookup`` cannot see a cluster, so those three values are redacted before
hashing. They are not part of the delta.

Expected delta, and nothing else:

- ``stoa-platform`` + ``values-staging.yaml``: ServiceMonitor
  ``stoa-control-plane-api`` environment label ``dev`` -> ``staging``
- ``stoa-platform`` + ``values-prod.yaml``: the same label ``dev`` -> ``prod``
- ``stoa-platform`` default and ``values-dev.yaml``: identical to main
- ``stoa-observability`` default, ``values-dev.yaml`` and ``values-prod.yaml``:
  identical to main
- ``stoa-stack`` does not exist on main. Its default render equals
  ``-f values.yaml``, and the shared environment label is ``dev``.

Run: python3 -B -m unittest discover -s charts/stoa-stack/tests -p test_render_delta_vs_main.py -v
"""

import hashlib
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml

CHARTS = Path(__file__).resolve().parents[2]
MAIN = "9199b3442fb8ffdb387c5cfc0934e88e867afe0f"
NAMESPACE = "stoa-system"
GENERATED_SECRET = re.compile(
    r"(?m)^(  (?:gateway-consumer-key|chat-internal-key|jwt-signing-key)): .+$"
)
CONTROL_PLANE_ENVIRONMENT = re.compile(
    r"(name: stoa-control-plane-api\n.*?targetLabel: environment\n          replacement: )(\S+)",
    re.S,
)

# scenario -> sha256 of the normalized main render. Staging and prod hashes are
# the main text, before the control-plane label moves to the overlay environment.
MAIN_SHA256 = {
    "stoa-platform--default": "5682526e88525a56d856b9158ffbbc6b9578c9e49c566f6e88957edfc765529a",
    "stoa-platform--values-dev": "ef7e07635d4404b6e13c2ac14673905341cc74f86ba9cd5ed035691bc50321c2",
    "stoa-platform--values-staging": "7d7177af98ad554a8c1f7bef8e9a94f1ce7c403d4612f035be8338bd6ab5baac",
    "stoa-platform--values-prod": "21aabdcfa75a185a0474612e3dc479c04f9c8149f45b70ac7ac2e8359828416a",
    "stoa-observability--default": "0e5f8e5a4ecba43f43404a219637e6d6f5ea394081de6a8f0ae045e534af9da7",
    "stoa-observability--values-dev": "a7518f140a9e6178c1cd626bbcfb2095a71d511c0e692d5f0630377bbf9192de",
    "stoa-observability--values-prod": "6044a25eac9f0c634f268fafe884ff9a271fb9e1c917b3fa058e25c59a756b1e",
}

# scenario -> (chart, values file or None, environment label on the combined render)
# None means this chart has no control-plane ServiceMonitor.
SCENARIOS = (
    ("stoa-platform--default", "stoa-platform", None, "dev"),
    ("stoa-platform--values-dev", "stoa-platform", "values-dev.yaml", "dev"),
    ("stoa-platform--values-staging", "stoa-platform", "values-staging.yaml", "staging"),
    ("stoa-platform--values-prod", "stoa-platform", "values-prod.yaml", "prod"),
    ("stoa-observability--default", "stoa-observability", None, None),
    ("stoa-observability--values-dev", "stoa-observability", "values-dev.yaml", None),
    ("stoa-observability--values-prod", "stoa-observability", "values-prod.yaml", None),
)


def helm(*arguments):
    executable = shutil.which("helm")
    if not executable:
        raise RuntimeError("Helm is required to compare rendered charts with main.")
    return subprocess.run([executable, *arguments], capture_output=True, text=True, check=False)


def normalize(text):
    return GENERATED_SECRET.sub(r"\1: REDACTED_GENERATED", text)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def render(chart, values=None):
    command = ["template", chart, str(CHARTS / chart), "--namespace", NAMESPACE]
    if values is not None:
        command += ["-f", str(CHARTS / chart / values)]
    result = helm(*command)
    if result.returncode != 0:
        raise AssertionError(f"helm {' '.join(command)} failed:\n{result.stderr}")
    return result.stdout


def control_plane_label(text):
    return [match.group(2) for match in CONTROL_PLANE_ENVIRONMENT.finditer(text)]


class CombinedRenderDeltaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = helm("dependency", "build", str(CHARTS / "stoa-stack"))
        if built.returncode != 0:
            raise AssertionError(f"helm dependency build failed:\n{built.stderr}")

    def test_renders_match_main_except_the_documented_environment_labels(self):
        for scenario, chart, values, label in SCENARIOS:
            with self.subTest(scenario=scenario):
                rendered = normalize(render(chart, values))
                found = control_plane_label(rendered)
                if label is None:
                    self.assertEqual(found, [])
                    comparable = rendered
                else:
                    self.assertEqual(found, [label], found)
                    # Main keeps the chart default "dev" on this ServiceMonitor.
                    # Staging and prod overlays now follow global.environment.
                    comparable = CONTROL_PLANE_ENVIRONMENT.sub(r"\1dev", rendered, count=1)
                self.assertEqual(
                    digest(comparable),
                    MAIN_SHA256[scenario],
                    f"{scenario} no longer matches main {MAIN} except the documented label",
                )

    def test_umbrella_default_render_matches_its_values_file(self):
        default = normalize(render("stoa-stack"))
        explicit = normalize(render("stoa-stack", "values.yaml"))
        self.assertEqual(default, explicit)
        self.assertEqual(control_plane_label(default), ["dev"])
        documents = [doc for doc in yaml.safe_load_all(default) if doc]
        gateway, = [doc for doc in documents
                    if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "stoa-gateway"]
        env = {item["name"]: item.get("value")
               for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["STOA_ENVIRONMENT"], "dev")
        alloy, = [doc for doc in documents
                  if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "stoa-alloy-config"]
        self.assertIn('environment = "dev"', alloy["data"]["config.alloy"])

    def test_helm_lint_accepts_default_and_environment_values(self):
        for scenario, chart, values, _label in SCENARIOS:
            with self.subTest(scenario=scenario):
                command = ["lint", str(CHARTS / chart)]
                if values is not None:
                    command += ["-f", str(CHARTS / chart / values)]
                result = helm(*command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = helm("lint", str(CHARTS / "stoa-stack"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
