# SPDX-License-Identifier: Apache-2.0
"""Docker-free checks for the identity HA proof.

    python3 -B -m unittest discover -s deploy/keycloak/ha-proof -p 'test_*.py' -v
"""

import contextlib
import io
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from verify_static import _docs, analyze, tolerated_losses

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "failover-proof.sh"
VERIFY = HERE / "verify_static.py"

READY_AFTER_LOSS = """\
READY kc-0 200
READY kc-1 200
READY kc-2 000
"""


def call(function, *args, stdin=""):
    """Run one helper of failover-proof.sh (sourced, main not executed)."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", function):
        raise AssertionError(function)
    result = subprocess.run(
        ["bash", "-c", f'source "$1"; shift; {function} "$@"', "bash", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


class RetainedSizing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = analyze()

    def test_reference_counts_and_base_unset(self):
        self.assertEqual(self.report.prod_replicas, 3)
        self.assertEqual(self.report.staging_replicas, 2)
        self.assertEqual(self.report.dev_replicas, 1)
        self.assertIsNone(self.report.base_replicas)

    def test_runnable_workloads_are_single_replica(self):
        self.assertEqual(self.report.compose_replicas, 1)
        self.assertTrue(self.report.compose_named)
        self.assertEqual(self.report.compose_cache, "ispn")
        self.assertIsNone(self.report.compose_cache_stack)
        self.assertTrue(self.report.compose_healthcheck)
        self.assertEqual(self.report.quickstart_replicas, 1)
        self.assertTrue(self.report.quickstart_dev_mode)
        self.assertIsNone(self.report.quickstart_cache)
        self.assertEqual(self.report.workloads, ())
        self.assertEqual(self.report.pdbs, ())

    def test_controls_absent_and_cache_not_shared(self):
        self.assertFalse(self.report.anti_affinity)
        self.assertFalse(self.report.k8s_probes)
        self.assertFalse(self.report.shared_cache)
        self.assertEqual(self.report.ha_static, "fail")
        self.assertEqual(tolerated_losses(3, False), 0)
        self.assertEqual(tolerated_losses(3, True), 2)
        self.assertEqual(tolerated_losses(1, True), 0)

    def test_gap_ids_match_the_criteria(self):
        self.assertEqual(
            [gap.id for gap in self.report.gaps],
            [
                "reference-only",
                "no-identity-workload",
                "no-keycloak-pdb",
                "no-anti-affinity",
                "no-k8s-probes",
                "compose-single-replica",
                "cache-not-shared",
                "quickstart-dev-mode",
            ],
        )
        pdb = next(gap.detail for gap in self.report.gaps if gap.id == "no-keycloak-pdb")
        self.assertIn("stoa-gateway", pdb)

    def test_shell_contract_has_no_secret_material(self):
        shell = self.report.shell()
        self.assertEqual(
            shell,
            "HA_STATIC=fail\n"
            "RETAINED_PROD_REPLICAS=3\n"
            "IN_REPO_REPLICAS=1\n"
            "SHARED_CACHE=false\n",
        )
        self.assertNotRegex(shell.lower(), r"password|secret|token|kubeconfig")
        text = self.report.text()
        self.assertIn("Still to prove live", text)
        self.assertIn("stoa-infra", text)
        self.assertNotRegex(text.lower(), r"password|begin private|kubeconfig")


class ProofScript(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_no_cluster_client_outside_comments(self):
        for line in SCRIPT.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            for forbidden in ("kubectl", "helm", "docker", "curl", "wget"):
                self.assertNotIn(forbidden, code, line)

    def test_sourcing_does_not_run_the_proof(self):
        code, out, err = call("true")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_tolerated_losses_follow_shared_cache(self):
        self.assertEqual(call("tolerated_losses", "3", "false")[1], "0")
        self.assertEqual(call("tolerated_losses", "3", "true")[1], "2")
        self.assertEqual(call("tolerated_losses", "1", "true")[1], "0")

    def test_failover_parser_requires_survivor_victim_and_session(self):
        held = call("failover_holds", "sess-a", "sess-a", "kc-2", stdin=READY_AFTER_LOSS)
        self.assertEqual(held[0], 0, held[2])
        moved = call("failover_holds", "sess-a", "sess-b", "kc-2", stdin=READY_AFTER_LOSS)
        self.assertNotEqual(moved[0], 0)
        wrong = call("failover_holds", "sess-a", "sess-a", "kc-0", stdin=READY_AFTER_LOSS)
        self.assertNotEqual(wrong[0], 0)

    def test_default_run_reports_not_proven(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not executed", result.stdout)
        self.assertIn("RESULT: NOT PROVEN", result.stdout)
        self.assertIn("tolerated_losses=0", result.stdout)
        self.assertNotRegex(result.stdout.lower(), r"password|secret")

    def test_execute_refuses_without_touching_a_cluster(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--execute"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("REFUSING live failover", result.stderr)
        self.assertNotIn("RESULT: NOT PROVEN", result.stdout)

    def test_verifier_cli(self):
        result = subprocess.run(
            ["python3", "-B", str(VERIFY), "--shell"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertRegex(result.stdout, re.compile(r"^HA_STATIC=fail\n"))


class UnparsedYaml(unittest.TestCase):
    def test_broken_yaml_is_reported_on_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.yaml"
            broken.write_text("kind: Deployment\n  replicas: [unclosed\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                text, docs = _docs(broken)
        self.assertEqual(docs, [])
        self.assertIn("kind: Deployment", text)
        self.assertIn("broken.yaml", stderr.getvalue())
        self.assertIn("YAML not parsed", stderr.getvalue())

    def test_templates_stay_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "template.yaml"
            template.write_text("kind: {{ .Values.kind }}\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                _, docs = _docs(template)
        self.assertEqual(docs, [])
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
