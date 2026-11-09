"""Offline coherence contracts for the stoa-stack umbrella chart.

Run: python3 -B -m unittest discover -s charts/stoa-stack/tests -v

The umbrella and its sibling charts are copied to a temporary directory and
their dependencies built there, so the repository tree is never modified and
no cluster or network access is needed.
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CHARTS = Path(__file__).resolve().parents[2]
UMBRELLA = "stoa-stack"
PLATFORM = "stoa-platform"
OBSERVABILITY = "stoa-observability"
SIBLINGS = (PLATFORM, OBSERVABILITY)
RELEASE = "stack"
NAMESPACE = "stoa-stack-test"
COMPANION_EXAMPLE = CHARTS / PLATFORM / "examples/companion-nginx.yaml"
SHARED_KEYS = {"environment", "clusterName", "otelEndpoint"}
# ServiceMonitors that carry shared labels when gateway, sidecar and API are on.
LABELLED_MONITORS = {"stoa-gateway", "nginx-stoa-sidecar", "stoa-control-plane-api"}

ALLOY_ENVIRONMENT = (
    re.compile(r'target_label\s*=\s*"environment"\s*\n\s*replacement\s*=\s*"([^"]*)"'),
    re.compile(r'^\s*environment\s*=\s*"([^"]*)",\s*$', re.MULTILINE),
    re.compile(r'key\s*=\s*"environment"\s*\n\s*value\s*=\s*"([^"]*)"'),
)


def helm(*arguments, cwd=None):
    executable = shutil.which("helm")
    if not executable:
        raise RuntimeError("Helm is required to run the umbrella chart contracts.")
    return subprocess.run([executable, *arguments], capture_output=True, text=True,
                          check=False, cwd=cwd)


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def documents(text):
    return [doc for doc in yaml.safe_load_all(text) if doc]


def find(objects, kind, name=None, **labels):
    found = [o for o in objects if o["kind"] == kind and
             (name is None or o["metadata"]["name"] == name) and
             all(o["metadata"].get("labels", {}).get(k) == v for k, v in labels.items())]
    return found


def container_env(workload, container):
    spec = workload["spec"]["template"]["spec"]
    target, = [c for c in spec["containers"] if c["name"] == container]
    return {item["name"]: item.get("value") for item in target.get("env", [])}


def relabel(service_monitor, label):
    values = {r["replacement"] for endpoint in service_monitor["spec"]["endpoints"]
              for r in endpoint.get("metricRelabelings", []) if r.get("targetLabel") == label}
    value, = values
    return value


def monitor_labels(objects, label):
    """Map ServiceMonitor name -> value for every monitor that sets ``label``."""
    return {m["metadata"]["name"]: relabel(m, label) for m in find(objects, "ServiceMonitor")
            if any(r.get("targetLabel") == label for e in m["spec"]["endpoints"]
                   for r in e.get("metricRelabelings", []))}


class UmbrellaChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._workspace = tempfile.TemporaryDirectory(prefix="stoa-stack-")
        root = Path(cls._workspace.name)
        for chart in (UMBRELLA, *SIBLINGS):
            shutil.copytree(CHARTS / chart, root / chart,
                            ignore=shutil.ignore_patterns("__pycache__", "charts")
                            if chart == UMBRELLA else shutil.ignore_patterns("__pycache__"))
        cls.umbrella = root / UMBRELLA
        build = helm("dependency", "build", str(cls.umbrella))
        if build.returncode != 0:
            cls._workspace.cleanup()
            raise AssertionError(f"helm dependency build failed:\n{build.stderr}")
        companion = load_yaml(COMPANION_EXAMPLE)
        companion["stoaSidecar"]["serviceMonitor"]["enabled"] = True
        cls.companion_values = root / "companion-umbrella-values.yaml"
        cls.companion_values.write_text(yaml.safe_dump({PLATFORM: companion}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._workspace.cleanup()

    def render(self, *arguments, chart=None, namespace=NAMESPACE):
        result = helm("template", RELEASE, str(chart or self.umbrella),
                      "--namespace", namespace, *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        return documents(result.stdout)

    def render_full(self, *arguments, **kwargs):
        """Umbrella render with gateway, sidecar and every ServiceMonitor active."""
        return self.render("-f", str(self.companion_values),
                           "--set", f"{PLATFORM}.controlPlaneApi.serviceMonitor.enabled=true",
                           *arguments, **kwargs)

    # -- shared parameters reach every consumer -----------------------------

    def environments(self, objects):
        gateway, = find(objects, "Deployment", "stoa-gateway")
        sidecar, = find(objects, "Deployment", "nginx-with-stoa-sidecar")
        alloy_config, = find(objects, "ConfigMap", "stoa-alloy-config")
        river = alloy_config["data"]["config.alloy"]
        alloy_values = [m for pattern in ALLOY_ENVIRONMENT for m in pattern.findall(river)]
        self.assertEqual(len(alloy_values), len(ALLOY_ENVIRONMENT), river)
        monitor_values = monitor_labels(objects, "environment")
        self.assertEqual(set(monitor_values), LABELLED_MONITORS)
        return {
            "gateway": container_env(gateway, "stoa-gateway")["STOA_ENVIRONMENT"],
            "sidecar": container_env(sidecar, "stoa-sidecar")["STOA_ENVIRONMENT"],
            **{f"monitor/{name}": value for name, value in monitor_values.items()},
            **{f"alloy/{index}": value for index, value in enumerate(alloy_values)},
        }

    def test_environment_is_derived_from_one_global_value(self):
        for environment in ("staging", "qa-eu-1"):
            with self.subTest(environment=environment):
                found = self.environments(self.render_full(
                    "--set", f"global.environment={environment}"))
                self.assertEqual(set(found.values()), {environment}, found)

    def test_environment_default_is_coherent_across_charts(self):
        found = self.environments(self.render_full())
        expected = load_yaml(self.umbrella / "values.yaml")["global"]["environment"]
        self.assertEqual(set(found.values()), {expected}, found)

    def test_global_environment_overrides_component_local_values(self):
        found = self.environments(self.render_full(
            "--set", "global.environment=prod",
            "--set", f"{PLATFORM}.stoaGateway.environment=local-gateway",
            "--set", f"{PLATFORM}.controlPlaneApi.environment=local-api",
            "--set", f"{OBSERVABILITY}.global.environment=local-observability"))
        self.assertEqual(set(found.values()), {"prod"}, found)

    def test_cluster_name_is_derived_from_one_global_value(self):
        objects = self.render_full("--set", "global.clusterName=eu-west-blue",
                                   "--set", f"{PLATFORM}.stoaGateway.clusterName=local")
        found = monitor_labels(objects, "cluster")
        self.assertEqual(set(found), LABELLED_MONITORS)
        self.assertEqual(set(found.values()), {"eu-west-blue"}, found)

    # -- cross-chart wiring: platform -> observability ---------------------

    def otlp_service(self, objects):
        service, = find(objects, "Service", **{"app.kubernetes.io/component": "otlp-receiver"})
        port, = [p for p in service["spec"]["ports"] if p["name"] == "otlp-grpc"]
        return service, port

    def otel_endpoints(self, objects):
        gateway, = find(objects, "Deployment", "stoa-gateway")
        sidecar, = find(objects, "Deployment", "nginx-with-stoa-sidecar")
        return {
            "gateway": container_env(gateway, "stoa-gateway").get("STOA_OTEL_ENDPOINT"),
            "sidecar": container_env(sidecar, "stoa-sidecar").get("STOA_OTEL_ENDPOINT"),
        }

    def test_otel_endpoint_targets_the_rendered_collector_service(self):
        objects = self.render_full()
        service, port = self.otlp_service(objects)
        self.assertEqual(service["metadata"]["namespace"], NAMESPACE)
        expected = f"http://{service['metadata']['name']}.{NAMESPACE}:{port['port']}"
        self.assertEqual(set(self.otel_endpoints(objects).values()), {expected})

    def test_otel_endpoint_follows_external_collector_namespace(self):
        objects = self.render_full("--set", "global.observability.namespace=telemetry")
        service, port = self.otlp_service(objects)
        expected = f"http://{service['metadata']['name']}.telemetry:{port['port']}"
        self.assertEqual(set(self.otel_endpoints(objects).values()), {expected})

    def test_network_policy_egress_matches_the_collector(self):
        objects = self.render_full("--set", f"{PLATFORM}.networkPolicy.enabled=true")
        service, port = self.otlp_service(objects)
        collector, = find(objects, "DaemonSet")
        pod_labels = collector["spec"]["template"]["metadata"]["labels"]
        for selector_key, selector_value in service["spec"]["selector"].items():
            self.assertEqual(pod_labels.get(selector_key), selector_value)
        policies = find(objects, "NetworkPolicy")
        self.assertEqual(len(policies), 2)
        for policy in policies:
            with self.subTest(policy=policy["metadata"]["name"]):
                otel = [rule for rule in policy["spec"]["egress"]
                        if rule["to"][0].get("namespaceSelector", {}).get("matchLabels", {})
                        .get("kubernetes.io/metadata.name") == NAMESPACE and
                        rule["ports"] == [{"port": port["targetPort"], "protocol": "TCP"}]]
                self.assertEqual(len(otel), 1, policy["spec"]["egress"])
                for key, value in otel[0]["to"][0]["podSelector"]["matchLabels"].items():
                    self.assertEqual(pod_labels.get(key), value)

    def test_disabling_observability_removes_chart_and_wiring(self):
        objects = self.render_full("--set", "global.observability.enabled=false",
                                   "--set", f"{PLATFORM}.networkPolicy.enabled=true")
        self.assertEqual([o for o in objects if o["metadata"].get("labels", {})
                          .get("helm.sh/chart", "").startswith(OBSERVABILITY)], [])
        self.assertEqual(find(objects, "DaemonSet"), [])
        self.assertEqual(set(self.otel_endpoints(objects).values()), {None})
        for policy in find(objects, "NetworkPolicy"):
            ports = [p["port"] for rule in policy["spec"]["egress"] for p in rule["ports"]]
            self.assertNotIn(4317, ports)

    # -- standalone charts keep their component-local fallbacks -------------

    def test_standalone_platform_uses_component_values(self):
        # CAB-2563 leaves the component environment empty so a standalone
        # install inherits global.environment. A non-empty component value
        # still wins in that mode; the umbrella tests cover global winning.
        objects = self.render("-f", str(COMPANION_EXAMPLE), chart=CHARTS / PLATFORM)
        values = load_yaml(CHARTS / PLATFORM / "values.yaml")
        self.assertEqual(self.otel_endpoints(objects), {
            "gateway": values["stoaGateway"]["otelEndpoint"],
            "sidecar": values["stoaSidecar"]["otelEndpoint"],
        })
        gateway, = find(objects, "Deployment", "stoa-gateway")
        component_environment = values["stoaGateway"]["environment"]
        expected = component_environment or values["global"]["environment"]
        self.assertEqual(container_env(gateway, "stoa-gateway")["STOA_ENVIRONMENT"], expected)

    def test_standalone_overlays_label_every_component_with_their_global_environment(self):
        for overlay in ("dev", "staging", "prod"):
            with self.subTest(overlay=overlay):
                path = CHARTS / PLATFORM / f"values-{overlay}.yaml"
                expected = load_yaml(path)["global"]["environment"]
                objects = self.render("-f", str(path), chart=CHARTS / PLATFORM)
                labels = monitor_labels(objects, "environment")
                self.assertEqual(set(labels), {"stoa-gateway", "stoa-control-plane-api"})
                self.assertEqual(set(labels.values()), {expected}, labels)

    # -- static guards against re-introduced duplication --------------------

    def test_dependency_versions_match_sibling_charts(self):
        chart = load_yaml(self.umbrella / "Chart.yaml")
        lock = load_yaml(self.umbrella / "Chart.lock")
        declared = {d["name"]: d for d in chart["dependencies"]}
        self.assertEqual(set(declared), set(SIBLINGS))
        locked = {d["name"]: d["version"] for d in lock["dependencies"]}
        for name in SIBLINGS:
            with self.subTest(chart=name):
                sibling = load_yaml(CHARTS / name / "Chart.yaml")
                self.assertEqual(declared[name]["repository"], f"file://../{name}")
                self.assertEqual(declared[name]["version"], sibling["version"])
                self.assertEqual(locked[name], sibling["version"])
        self.assertEqual(declared[OBSERVABILITY]["condition"], "global.observability.enabled")

    def test_umbrella_values_define_shared_keys_only_under_global(self):
        def offending(node, path):
            if not isinstance(node, dict):
                return []
            hits = [f"{path}.{k}" for k in node if k in SHARED_KEYS]
            return hits + [h for k, v in node.items() for h in offending(v, f"{path}.{k}")]

        values = load_yaml(CHARTS / UMBRELLA / "values.yaml")
        self.assertTrue(SHARED_KEYS - {"otelEndpoint"} <= set(values["global"]))
        self.assertIn("enabled", values["global"]["observability"])
        self.assertEqual(offending({k: v for k, v in values.items() if k != "global"}, ""), [])

    def test_platform_templates_read_shared_values_through_helpers(self):
        field = re.compile(r"\.(environment|clusterName|otelEndpoint)\b")
        offenders = []
        for template in sorted((CHARTS / PLATFORM / "templates").glob("*.yaml")):
            for number, line in enumerate(template.read_text(encoding="utf-8").splitlines(), 1):
                if ".Values" not in line and "$config" not in line:
                    continue
                if field.search(line) and "include \"stoa-platform." not in line:
                    offenders.append(f"{template.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
