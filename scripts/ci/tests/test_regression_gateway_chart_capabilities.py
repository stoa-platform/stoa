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


def assert_image_build_contract(workflow, dockerfile):
    """Check the local build manifest; never pull or execute an image.

    This deliberately follows the current multi-stage Dockerfile contract.
    A build-layout change must update the assertions rather than silently skip them.
    """
    steps = workflow["jobs"]["docker"]["steps"]
    builds = [step for step in steps if step.get("id") == "build"]
    assert len(builds) == 1, "Expected one image build step"
    build = builds[0]
    assert build["uses"].startswith("docker/build-push-action@")
    assert "${{ inputs.build-args }}" in build["with"]["build-args"], "Image features not forwarded"
    assert build["with"]["file"] == "${{ format('{0}/Dockerfile', inputs.component) }}"

    # Ignore comments and join continuations so comments cannot satisfy the contract.
    source = "\n".join(
        line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
    )
    source = source.replace("\\\n", " ")
    stages = re.split(r"(?im)^FROM .+ AS (\w+)\s*$", source)
    by_name = dict(zip(stages[1::2], stages[2::2], strict=True))
    builder = by_name["builder"]
    runtime = by_name["runtime"]
    assert re.search(r"(?m)^ARG FEATURES=", builder), "Builder does not accept image features"
    assert re.search(r'cargo build --locked --release --features "\$\{FEATURES\}"', builder), (
        "Release binary ignores image features"
    )
    assert re.search(r"(?m)^COPY policies ./policies$", builder), "Embedded policy sources missing"
    assert re.search(r"(?m)^COPY src ./src$", builder), "Gateway sources missing"
    assert re.search(
        r"(?m)^COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway$", runtime
    ), "Runtime does not ship the checked release binary"
    assert re.search(r'(?m)^ENTRYPOINT \["/app/stoa-gateway"\]$', runtime)
    users = re.findall(r"(?m)^USER (.+)$", runtime)
    assert users and users[-1] == "1000", "Runtime must retain the non-root user"


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

    def test_regression_image_build_preserves_policy_capabilities(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-docker-ghcr.yml").read_text())
        dockerfile = (ROOT / "stoa-gateway/Dockerfile").read_text()
        assert_image_build_contract(workflow, dockerfile)

    def test_broken_image_build_contract_is_rejected(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-docker-ghcr.yml").read_text())
        dockerfile = (ROOT / "stoa-gateway/Dockerfile").read_text()
        mutations = {
            "features ignored": ('--features "${FEATURES}"', ""),
            "policy omitted": ("COPY policies ./policies", "# COPY policies ./policies"),
            "wrong binary": ("/app/target/release/stoa-gateway", "/app/target/debug/stoa-gateway"),
            "root runtime": ("USER 1000", "USER 0"),
        }
        for name, (before, after) in mutations.items():
            with self.subTest(regression=name), self.assertRaises(AssertionError):
                assert_image_build_contract(workflow, dockerfile.replace(before, after))
        build = next(
            step for step in workflow["jobs"]["docker"]["steps"] if step.get("id") == "build"
        )
        build["with"]["build-args"] = "CACHEBUST=${{ github.sha }}"
        with self.assertRaisesRegex(AssertionError, "features not forwarded"):
            assert_image_build_contract(workflow, dockerfile)

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
