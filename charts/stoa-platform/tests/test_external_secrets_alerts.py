"""ESO sync alerts: python3 -m unittest discover -s charts/stoa-platform/tests -p test_external_secrets_alerts.py -v.

Render contracts run with helm only. The rule tests also need promtool; they
are skipped when it is not installed.
"""

import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = "templates/external-secrets-prometheusrule.yaml"
ALERTS = ["ExternalSecretNotReady", "ExternalSecretSyncErrors", "SecretStoreNotReady"]


def render(*sets):
    command = ["helm", "template", "eso-test", str(CHART), "--namespace", "stoa-system"]
    for value in sets:
        command += ["--set", value]
    docs = yaml.safe_load_all(subprocess.check_output(command, text=True))
    return [d for d in docs if d and d.get("kind") == "PrometheusRule" and d["metadata"]["name"] == "external-secrets-alerts"]


def enabled(*sets):
    return render("externalSecrets.monitoring.prometheusRule.enabled=true", *sets)


class RenderTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(render(), [])

    def test_enabled_renders_three_alerts(self):
        (rule,) = enabled()
        self.assertEqual(rule["metadata"]["namespace"], "stoa-system")
        (group,) = rule["spec"]["groups"]
        self.assertEqual([r["alert"] for r in group["rules"]], ALERTS)
        severities = {r["alert"]: r["labels"]["severity"] for r in group["rules"]}
        self.assertEqual(severities["SecretStoreNotReady"], "critical")
        for r in group["rules"]:
            self.assertIn("{{ $labels.name }}", r["annotations"]["description"])

    def test_namespace_and_durations_are_configurable(self):
        (rule,) = enabled(
            "externalSecrets.monitoring.namespace=monitoring",
            "externalSecrets.monitoring.prometheusRule.notReadyFor=5m",
        )
        self.assertEqual(rule["metadata"]["namespace"], "monitoring")
        self.assertEqual(rule["spec"]["groups"][0]["rules"][0]["for"], "5m")


RULE_TESTS = textwrap.dedent(
    """
    rule_files: [rules.yaml]
    evaluation_interval: 1m
    tests:
      - interval: 1m
        input_series:
          - series: 'externalsecret_status_condition{namespace="stoa-system",name="gw",condition="Ready",status="False"}'
            values: '1x40'
          - series: 'externalsecret_status_condition{namespace="stoa-system",name="ok",condition="Ready",status="False"}'
            values: '0x40'
        alert_rule_test:
          - eval_time: 10m
            alertname: ExternalSecretNotReady
            exp_alerts: []
          - eval_time: 20m
            alertname: ExternalSecretNotReady
            exp_alerts:
              - exp_labels: {severity: warning, namespace: stoa-system, name: gw}
                exp_annotations:
                  summary: ExternalSecret is not synced
                  description: >-
                    ExternalSecret stoa-system/gw has failed to sync. The Kubernetes Secret keeps
                    its last synced value; rotations are not applied and new pods start with that value.
      - interval: 1m
        input_series:
          - series: 'externalsecret_sync_calls_error{namespace="stoa-system",name="gw"}'
            values: '0+1x80'
          - series: 'externalsecret_sync_calls_error{namespace="stoa-system",name="ok"}'
            values: '3x80'
        alert_rule_test:
          - eval_time: 30m
            alertname: ExternalSecretSyncErrors
            exp_alerts: []
          - eval_time: 60m
            alertname: ExternalSecretSyncErrors
            exp_alerts:
              - exp_labels: {severity: warning, namespace: stoa-system, name: gw}
                exp_annotations:
                  summary: ExternalSecret sync calls are failing
                  description: >-
                    ExternalSecret stoa-system/gw keeps reporting sync errors. Check the secrets
                    store and the SecretStore credentials.
      - interval: 1m
        input_series:
          - series: 'clustersecretstore_status_condition{name="vault-backend",condition="Ready",status="False"}'
            values: '1x20'
          - series: 'secretstore_status_condition{namespace="stoa-system",name="local",condition="Ready",status="False"}'
            values: '0x20'
        alert_rule_test:
          - eval_time: 5m
            alertname: SecretStoreNotReady
            exp_alerts: []
          - eval_time: 15m
            alertname: SecretStoreNotReady
            exp_alerts:
              - exp_labels: {severity: critical, name: vault-backend}
                exp_annotations:
                  summary: SecretStore is not ready
                  description: >-
                    SecretStore vault-backend is not ready: no ExternalSecret using it can sync.
                    Existing Secrets keep their last values.
    """
)


@unittest.skipUnless(shutil.which("promtool"), "promtool not installed")
class PromtoolTests(unittest.TestCase):
    def setUp(self):
        (rule,) = enabled()
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "rules.yaml").write_text(yaml.safe_dump(rule["spec"]))
        (self.dir / "tests.yaml").write_text(RULE_TESTS)

    def promtool(self, *args):
        return subprocess.run(["promtool", *args], cwd=self.dir, capture_output=True, text=True)

    def test_rules_are_valid(self):
        result = self.promtool("check", "rules", "rules.yaml")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_alerts_fire_only_after_their_delay(self):
        result = self.promtool("test", "rules", "tests.yaml")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
