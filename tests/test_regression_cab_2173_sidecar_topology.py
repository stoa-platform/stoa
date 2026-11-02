# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Offline topology contracts: python3 -m unittest discover -s tests -p 'test_regression_cab_2173*.py'."""

import json
import unittest
from pathlib import Path

import yaml
from scripts.security.helm_contract_support import render

ROOT = Path(__file__).resolve().parents[1]


def literal_env(container):
    return {entry["name"]: entry["value"] for entry in container["env"] if "value" in entry}


class SidecarTopologyTests(unittest.TestCase):
    def manifests(self, *arguments):
        result = render(*arguments)
        self.assertEqual(result.returncode, 0, "Local Helm rendering failed")
        return [obj for obj in yaml.safe_load_all(result.stdout) if obj]

    def test_regression_cab_2173_sidecar_is_opt_in(self):
        manifests = self.manifests()
        self.assertFalse(
            any(
                obj["metadata"].get("labels", {}).get("stoa.io/deployment-kind") == "sidecar"
                for obj in manifests
            )
        )

    def test_regression_cab_2173_enabled_sidecar_has_same_pod_proof(self):
        manifests = self.manifests("--set", "stoaSidecar.enabled=true")
        deployment = next(
            obj
            for obj in manifests
            if obj["kind"] == "Deployment"
            and obj["metadata"]["labels"].get("stoa.io/deployment-kind") == "sidecar"
        )
        pod = deployment["spec"]["template"]
        containers = {container["name"]: container for container in pod["spec"]["containers"]}
        self.assertEqual(set(containers), {"webmethods", "stoa-sidecar"})
        self.assertEqual(pod["metadata"]["annotations"]["stoa.io/topology"], "same-pod-sidecar")
        gateway_env = literal_env(containers["webmethods"])
        sidecar_env = literal_env(containers["stoa-sidecar"])
        self.assertEqual(gateway_env["EXT_AUTHZ_URL"], "http://localhost:8081/authz")
        self.assertEqual(sidecar_env["STOA_GATEWAY_MODE"], "sidecar")
        self.assertEqual(sidecar_env["STOA_DEPLOYMENT_MODE"], "sidecar")
        self.assertEqual(sidecar_env["STOA_TARGET_GATEWAY_TYPE"], "webmethods")
        self.assertEqual(sidecar_env["STOA_TOPOLOGY"], "same-pod")
        proof = json.loads(sidecar_env["STOA_TOPOLOGY_PROOF"])
        self.assertEqual(set(proof["containers"]), set(containers))
        self.assertEqual(proof["target_container"], "webmethods")
        self.assertEqual(proof["sidecar_container"], "stoa-sidecar")
        self.assertEqual(proof["deployment"], deployment["metadata"]["name"])
        self.assertEqual(proof["authz_url"], gateway_env["EXT_AUTHZ_URL"])

    def test_regression_cab_2173_sidecar_without_target_fails_render(self):
        result = render(
            "--set", "stoaSidecar.enabled=true", "--set", "stoaSidecar.mainGateway.enabled=false"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires stoaSidecar.mainGateway.enabled=true", result.stderr)

    def test_regression_cab_2173_remote_link_declares_connect_topology(self):
        deployment = yaml.safe_load(
            (ROOT / "k8s/gateways/base/stoa-link-wm/deployment.yaml").read_text()
        )
        pod = deployment["spec"]["template"]
        self.assertEqual(
            deployment["metadata"]["labels"]["stoa.io/deployment-kind"], "standalone-link"
        )
        self.assertEqual(pod["metadata"]["labels"]["stoa.io/deployment-kind"], "standalone-link")
        self.assertEqual(deployment["metadata"]["labels"]["stoa.io/runtime-mode"], "sidecar")
        self.assertEqual(pod["metadata"]["labels"]["stoa.io/runtime-mode"], "sidecar")
        self.assertEqual(
            pod["metadata"]["annotations"]["stoa.io/topology"], "standalone-remote-link"
        )
        self.assertEqual(len(pod["spec"]["containers"]), 1)
        environment = literal_env(pod["spec"]["containers"][0])
        # Runtime routes and deployment topology are separate contracts.
        self.assertEqual(environment["STOA_GATEWAY_MODE"], "sidecar")
        self.assertEqual(environment.get("STOA_DEPLOYMENT_MODE"), "connect")
        self.assertEqual(environment.get("STOA_TARGET_GATEWAY_TYPE"), "webmethods")
        self.assertEqual(environment.get("STOA_TOPOLOGY"), "remote-agent")
        self.assertNotIn("STOA_TOPOLOGY_PROOF", environment)
