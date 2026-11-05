"""Keep rendered Helm capabilities compatible with the published gateway image."""

import re
import shlex
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "charts/stoa-platform"
WORKFLOW = ROOT / ".github/workflows/stoa-gateway-ci.yml"
# Policy evaluation is unconditional; only these chart switches need Cargo features.
FEATURE_GATES = {"STOA_K8S_ENABLED": "k8s", "STOA_KAFKA_ENABLED": "kafka"}


def image_features(workflow):
    arguments = workflow["jobs"]["docker"]["with"]["build-args"]
    matches = re.findall(r"^\s*FEATURES=(.*)$", arguments, re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError("Published image must declare exactly one FEATURES argument")
    return set(filter(None, re.split(r"[,\s]+", matches[0].strip().strip("\"'"))))


def missing_features(documents, features):
    missing = set()
    for document in documents:
        if not document or document.get("kind") != "Deployment":
            continue
        for container in document["spec"]["template"]["spec"]["containers"]:
            if container["name"] != "stoa-gateway":
                continue
            for variable in container.get("env", []):
                feature = FEATURE_GATES.get(variable["name"])
                if feature and str(variable.get("value")).lower() == "true":
                    if feature not in features:
                        missing.add(feature)
    return missing


class GatewayChartCapabilitiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(WORKFLOW.read_text())
        cls.features = image_features(cls.workflow)

    def test_regression_chart_profiles_match_published_image(self):
        for values in sorted(CHART.glob("values*.yaml")):
            with self.subTest(profile=values.name):
                result = subprocess.run(
                    ["helm", "template", "capabilities", str(CHART), "-f", str(values)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertFalse(
                    missing_features(yaml.safe_load_all(result.stdout), self.features),
                    "Chart enables capabilities missing from published image FEATURES",
                )

    def test_rust_ci_covers_published_features(self):
        flags = shlex.split(self.workflow["jobs"]["ci"]["with"]["cargo-features"])
        if "--all-features" in flags:
            return
        self.assertIn("--features", flags)
        tested = set(flags[flags.index("--features") + 1].replace(",", " ").split())
        self.assertLessEqual(self.features, tested)

    def test_missing_feature_is_rejected(self):
        for variable, feature in FEATURE_GATES.items():
            with self.subTest(feature=feature):
                documents = [
                    {
                        "kind": "Deployment",
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "stoa-gateway",
                                            "env": [{"name": variable, "value": "true"}],
                                        }
                                    ]
                                }
                            }
                        },
                    }
                ]
                self.assertEqual(missing_features(documents, set()), {feature})
                self.assertFalse(missing_features(documents, {feature}))
                documents[0]["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = (
                    "false"
                )
                self.assertFalse(missing_features(documents, set()))


if __name__ == "__main__":
    unittest.main()
