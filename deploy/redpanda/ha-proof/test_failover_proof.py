# SPDX-License-Identifier: Apache-2.0
"""Static and unit checks for the messaging HA failover proof.

Runs without Docker: validates that the compose topology and the proof script
match the retained sizing documented in the runbooks, and exercises the
script's output parsers on recorded rpk output shapes. The live failover run
is failover-proof.sh itself.

    python3 -m unittest discover -s deploy/redpanda/ha-proof -p 'test_*.py'
"""
import re
import subprocess
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
COMPOSE = HERE / "docker-compose.yml"
SCRIPT = HERE / "failover-proof.sh"
TOPICS_RUNBOOK = REPO / "docs/runbooks/kafka-topics.md"
OPS_RUNBOOK = REPO / "docs/runbooks/event-backbone-ops.md"
CHART_VALUES = REPO / "deploy/redpanda/values.yaml"
K8S_MANIFEST = REPO / "k8s/redpanda/statefulset.yaml"

CLUSTER_INFO = """\
CLUSTER
=======
redpanda.5f1c7a52-0d37-4bd4-9d5e-1f0a8e0c4b11

BROKERS
=======
ID    HOST        PORT
0*    redpanda-0  9092
1     redpanda-1  9092
2     redpanda-2  9092

TOPICS
======
NAME                    PARTITIONS  REPLICAS
stoa.ha.failover-proof  3           3
"""

TOPIC_DESCRIBE = """\
PARTITION  LEADER  EPOCH  REPLICAS  LOG-START-OFFSET  HIGH-WATERMARK
0          2       1      [0 1 2]   0                 17
1          0       1      [0 1 2]   0                 16
2          -1      2      [0 1 2]   0                 17
"""

HEALTH_DEGRADED = """\
CLUSTER HEALTH OVERVIEW
=======================
Healthy:                          false
Unhealthy reasons:                [nodes_down]
Controller ID:                    0
All nodes:                        [0 1 2]
Nodes down:                       [2]
Leaderless partitions (0):        []
Under-replicated partitions (3):  [kafka/stoa.ha.failover-proof/0 kafka/stoa.ha.failover-proof/1 kafka/stoa.ha.failover-proof/2]
"""

HEALTH_OK = """\
CLUSTER HEALTH OVERVIEW
=======================
Healthy:                          true
Unhealthy reasons:                []
Controller ID:                    0
All nodes:                        [0 1 2]
Nodes down:                       []
Leaderless partitions (0):        []
Under-replicated partitions (0):  []
"""


def script_var(name):
    match = re.search(rf"^{name}=\"?([^\"\n]+)\"?$", SCRIPT.read_text(), re.M)
    if not match:
        raise AssertionError(f"{name} not set in {SCRIPT.name}")
    return match[1]


def call(function, *args, stdin=""):
    """Run one helper of failover-proof.sh (sourced, main not executed)."""
    result = subprocess.run(
        ["bash", "-c", f'source "$1"; shift; {function} "$@"', "bash", str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True, check=False,
    )
    return result.returncode, result.stdout.strip()


class RetainedSizing(unittest.TestCase):
    """The proof exercises the sizing already retained by the runbooks."""

    def test_runbooks_retain_rf3_and_two_insync_replicas(self):
        topics = TOPICS_RUNBOOK.read_text()
        self.assertRegex(topics, r"\*\*Replication Factor \(RF\)\*\*: 3\b")
        self.assertRegex(topics, r"\*\*min\.insync\.replicas\*\*: 2\b")
        ops = OPS_RUNBOOK.read_text()
        self.assertIn("`replication.factor`: 3 (production)", ops)
        self.assertIn("`min.insync.replicas`: 2 (production)", ops)

    def test_chart_values_retain_three_brokers_for_production(self):
        values = CHART_VALUES.read_text()
        self.assertRegex(values, r"#\s*- Set statefulset\.replicas: 3\b")
        self.assertRegex(values, r"#\s*- Set replication\.factor=3\b")

    def test_script_constants_match_retained_sizing(self):
        self.assertEqual(script_var("BROKER_COUNT"), "3")
        self.assertEqual(script_var("REPLICATION_FACTOR"), "3")
        self.assertEqual(script_var("MIN_INSYNC_REPLICAS"), "2")
        brokers = re.search(r"^BROKERS=\(([^)]*)\)$", SCRIPT.read_text(), re.M)[1].split()
        self.assertEqual(brokers, sorted(yaml.safe_load(COMPOSE.read_text())["services"]))

    def test_quorum_tolerates_exactly_one_broker_loss(self):
        self.assertEqual(call("majority", "3"), (0, "2"))
        self.assertEqual(call("tolerated_failures", "3"), (0, "1"))
        # The single-broker shape of values.yaml / the k8s manifest tolerates nothing.
        self.assertEqual(call("tolerated_failures", "1"), (0, "0"))


class ComposeTopology(unittest.TestCase):
    """docker-compose.yml is a faithful, local-only three-broker cluster."""

    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load(COMPOSE.read_text())
        cls.services = cls.compose["services"]

    def flags(self, name):
        command = self.services[name]["command"]
        self.assertEqual(command[:2], ["redpanda", "start"])
        return dict(arg.split("=", 1) for arg in command[2:] if "=" in arg)

    def test_three_brokers_same_pinned_release_as_k8s_manifest(self):
        self.assertEqual(sorted(self.services), ["redpanda-0", "redpanda-1", "redpanda-2"])
        k8s_tag = re.search(r"redpandadata/redpanda:(v[\d.]+)", K8S_MANIFEST.read_text())[1]
        images = {svc["image"] for svc in self.services.values()}
        self.assertEqual(len(images), 1)
        image = images.pop()
        self.assertRegex(image, rf"^redpandadata/redpanda:{re.escape(k8s_tag)}@sha256:[0-9a-f]{{64}}$")

    def test_each_broker_advertises_its_own_address(self):
        for name in self.services:
            flags = self.flags(name)
            self.assertEqual(self.services[name]["hostname"], name)
            self.assertEqual(flags["--advertise-kafka-addr"], f"internal://{name}:9092")
            self.assertEqual(flags["--rpc-addr"], f"{name}:33145")
            self.assertEqual(flags["--advertise-rpc-addr"], f"{name}:33145")

    def test_brokers_form_one_cluster(self):
        self.assertNotIn("--seeds", self.flags("redpanda-0"))
        for name in ("redpanda-1", "redpanda-2"):
            self.assertEqual(self.flags(name)["--seeds"], "redpanda-0:33145")
            self.assertIn("redpanda-0", self.services[name]["depends_on"])

    def test_local_only_no_published_port_volume_or_restart(self):
        for name, svc in self.services.items():
            self.assertNotIn("ports", svc, name)
            self.assertNotIn("volumes", svc, name)
            self.assertNotIn("container_name", svc, name)
            # A restart policy would hide the broker loss the proof injects.
            self.assertEqual(svc["restart"], "no", name)
        self.assertNotIn("volumes", self.compose)


class ProofScript(unittest.TestCase):
    """failover-proof.sh parsers and invariants."""

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_writes_require_all_replicas_ack(self):
        self.assertIn("topic produce \"$TOPIC\" --acks=-1", SCRIPT.read_text())

    def test_broker_host_maps_node_id_including_controller(self):
        self.assertEqual(call("broker_host", "0", stdin=CLUSTER_INFO), (0, "redpanda-0"))
        self.assertEqual(call("broker_host", "2", stdin=CLUSTER_INFO), (0, "redpanda-2"))
        self.assertEqual(call("broker_host", "3", stdin=CLUSTER_INFO), (0, ""))

    def test_partition_leaders_include_leaderless(self):
        self.assertEqual(call("partition_leaders", stdin=TOPIC_DESCRIBE), (0, "0 2\n1 0\n2 -1"))

    def test_health_parsers(self):
        self.assertEqual(call("nodes_down", stdin=HEALTH_DEGRADED), (0, "2"))
        self.assertEqual(call("nodes_down", stdin=HEALTH_OK), (0, ""))
        self.assertEqual(call("node_count", stdin=HEALTH_DEGRADED), (0, "3"))
        self.assertEqual(call("is_healthy", stdin=HEALTH_OK)[0], 0)
        self.assertNotEqual(call("is_healthy", stdin=HEALTH_DEGRADED)[0], 0)

    def test_sourcing_does_not_run_the_proof(self):
        self.assertEqual(call("true"), (0, ""))


if __name__ == "__main__":
    unittest.main()
