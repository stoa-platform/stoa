"""Offline render contracts: python3 -m unittest discover -s charts/stoa-platform/tests -v."""
import pathlib
import subprocess
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]


def render(**values):
    command = ["helm", "template", "policy-test", str(CHART), "--namespace", "stoa-system"]
    for key, value in values.items():
        command += ["--set", f"{key}={str(value).lower() if isinstance(value, bool) else value}"]
    return [doc for doc in yaml.safe_load_all(subprocess.check_output(command, text=True)) if doc]


class NetworkPolicyTests(unittest.TestCase):
    def policies(self, **values):
        values.setdefault("networkPolicy.enabled", True)
        return [d for d in render(**values) if d["kind"] == "NetworkPolicy"]

    def test_opt_in_and_disabled_workloads(self):
        self.assertEqual(self.policies(**{"networkPolicy.enabled": False}), [])
        self.assertEqual(self.policies(**{"stoaGateway.enabled": False}), [])

    def test_gateway_isolation_and_required_allows(self):
        policy, = self.policies()
        spec = policy["spec"]
        self.assertEqual(spec["podSelector"]["matchLabels"], {
            "app.kubernetes.io/name": "stoa-gateway",
            "app.kubernetes.io/instance": "policy-test",
        })
        self.assertEqual(spec["policyTypes"], ["Ingress", "Egress"])
        ingress = spec["ingress"]
        self.assertEqual([r["ports"] for r in ingress], [
            [{"port": 8080, "protocol": "TCP"}],
            [{"port": 8080, "protocol": "TCP"}],
            [{"port": 8080, "protocol": "TCP"}],
        ])
        self.assertEqual(ingress[0]["from"][0], {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}},
            "podSelector": {"matchLabels": {"app.kubernetes.io/component": "controller"}},
        })
        self.assertEqual(ingress[1]["from"][0]["podSelector"]["matchLabels"], {
            "app.kubernetes.io/name": "prometheus"})
        self.assertEqual(ingress[2]["from"][0]["podSelector"]["matchLabels"], {
            "app.kubernetes.io/component": "test", "app.kubernetes.io/instance": "policy-test"})
        dns, api, otel = spec["egress"]
        self.assertEqual(dns["ports"], [{"port": 53, "protocol": p} for p in ["UDP", "TCP"]])
        self.assertEqual(dns["to"][0], {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
        })
        self.assertEqual(api["ports"], [{"port": 8000, "protocol": "TCP"}])
        self.assertEqual(api["to"][0]["podSelector"], {"matchLabels": {"app": "stoa-control-plane-api"}})
        self.assertEqual(api["to"][0]["namespaceSelector"]["matchLabels"], {
            "kubernetes.io/metadata.name": "stoa-system"})
        self.assertEqual(otel["ports"], [{"port": 4317, "protocol": "TCP"}])
        self.assertEqual(otel["to"][0]["podSelector"], {
            "matchLabels": {"app.kubernetes.io/name": "alloy"}})
        for rule in spec["egress"] + spec["ingress"]:
            self.assertTrue(rule["ports"])
            for peer in rule.get("to", rule.get("from")):
                self.assertTrue(peer.get("podSelector") or peer.get("ipBlock"))

    def test_companion_uses_main_port_without_exposing_local_authz(self):
        policies = self.policies(**{
            "stoaSidecar.enabled": True,
            "stoaSidecar.mainGateway.image.repository": "example/gateway",
            "stoaSidecar.mainGateway.image.digest": "sha256:" + "a" * 64,
            "stoaSidecar.mainGateway.port": 9090,
        })
        self.assertEqual(len(policies), 2)
        companion = next(p for p in policies if p["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"] == "stoa-sidecar")
        self.assertEqual([r["ports"][0]["port"] for r in companion["spec"]["ingress"]], [9090])
        self.assertEqual(len(companion["spec"]["egress"]), 3)

    def test_custom_peer_namespaces_and_ports(self):
        policy, = self.policies(**{
            "networkPolicy.controlPlaneNamespace": "control",
            "networkPolicy.controlPlanePort": 9000,
            "networkPolicy.monitoringNamespace": "metrics",
            "networkPolicy.otelPort": 4318,
            "networkPolicy.ingressNamespace": "edge",
        })
        spec = policy["spec"]
        self.assertEqual(spec["ingress"][0]["from"][0]["namespaceSelector"]["matchLabels"], {
            "kubernetes.io/metadata.name": "edge"})
        for rule, namespace, port in zip(spec["egress"][1:], ["control", "metrics"], [9000, 4318]):
            self.assertEqual(rule["to"][0]["namespaceSelector"]["matchLabels"], {
                "kubernetes.io/metadata.name": namespace})
            self.assertEqual(rule["ports"], [{"port": port, "protocol": "TCP"}])
        documents = render(**{"networkPolicy.enabled": True})
        deployment = next(d for d in documents if d["kind"] == "Deployment")
        labels = deployment["spec"]["template"]["metadata"]["labels"]
        for key, value in spec["podSelector"]["matchLabels"].items():
            self.assertEqual(labels[key], value)

    def test_optional_telemetry_and_explicit_backend_egress(self):
        policy, = self.policies(**{
            "stoaGateway.otelEndpoint": "",
            "stoaGateway.serviceMonitor.enabled": False,
            "networkPolicy.gatewayEgress[0].to[0].ipBlock.cidr": "192.0.2.10/32",
            "networkPolicy.gatewayEgress[0].ports[0].port": 443,
            "networkPolicy.gatewayEgress[0].ports[0].protocol": "TCP",
        })
        self.assertEqual(len(policy["spec"]["ingress"]), 2)
        self.assertEqual(policy["spec"]["egress"][-1], {
            "to": [{"ipBlock": {"cidr": "192.0.2.10/32"}}],
            "ports": [{"port": 443, "protocol": "TCP"}],
        })
        self.assertEqual(len(policy["spec"]["egress"]), 3)


if __name__ == "__main__":
    unittest.main()
