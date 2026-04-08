# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""
Spec-driven tests for CAB-2007: Helm seeder hook for control-plane-api.

Tests validate the Helm template in stoa-infra and the rendered output.
AC1-AC10 from SPEC.md.

Run: pytest tests/test_spec_cab_2007_seeder_k8s.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
STOA_INFRA = REPO_ROOT.parent / "stoa-infra"
CHART_DIR = STOA_INFRA / "charts" / "control-plane-api"
TEMPLATE_FILE = CHART_DIR / "templates" / "seeder-job.yaml"
VALUES_FILE = CHART_DIR / "values.yaml"


# ---------------------------------------------------------------------------
# Helpers — parse Helm template (strip Go template directives for structure)
# ---------------------------------------------------------------------------


def _load_values() -> dict:
    """Load values.yaml from the chart."""
    assert VALUES_FILE.exists(), f"values.yaml not found: {VALUES_FILE}"
    with open(VALUES_FILE) as f:
        return yaml.safe_load(f)


def _load_template_raw() -> str:
    """Load the raw Helm template content."""
    assert TEMPLATE_FILE.exists(), f"Template not found: {TEMPLATE_FILE}"
    return TEMPLATE_FILE.read_text()


# ---------------------------------------------------------------------------
# AC1 + AC2: Template and values exist
# ---------------------------------------------------------------------------


class TestAC1AC2Exists:
    """AC1/AC2: Helm seeder template and values exist."""

    def test_ac1_template_exists(self):
        assert TEMPLATE_FILE.exists(), (
            f"Seeder template not found at {TEMPLATE_FILE}"
        )

    def test_ac2_values_have_seeder_config(self):
        values = _load_values()
        assert "seeder" in values, "values.yaml must have a 'seeder' section"
        seeder = values["seeder"]
        assert "enabled" in seeder
        assert "profile" in seeder


# ---------------------------------------------------------------------------
# AC3: Uses same image as deployment
# ---------------------------------------------------------------------------


class TestAC3Image:
    """AC3: Seeder uses the same image as the control-plane-api deployment."""

    def test_ac3_image_uses_values(self):
        raw = _load_template_raw()
        assert ".Values.image.repository" in raw, (
            "Seeder must use .Values.image.repository"
        )
        assert ".Values.image.tag" in raw, (
            "Seeder must use .Values.image.tag"
        )


# ---------------------------------------------------------------------------
# AC4: DATABASE_URL from secret
# ---------------------------------------------------------------------------


class TestAC4SecretRef:
    """AC4: Seeder reads DATABASE_URL from the existing secret."""

    def test_ac4_envfrom_secret(self):
        raw = _load_template_raw()
        assert ".Values.secrets.existingSecret" in raw, (
            "Seeder must use envFrom with .Values.secrets.existingSecret"
        )
        assert "envFrom" in raw


# ---------------------------------------------------------------------------
# AC5: backoffLimit and activeDeadlineSeconds
# ---------------------------------------------------------------------------


class TestAC5Limits:
    """AC5: Default values have backoffLimit: 1, activeDeadlineSeconds: 120."""

    def test_ac5_default_backoff_limit(self):
        values = _load_values()
        assert values["seeder"]["backoffLimit"] == 1

    def test_ac5_default_deadline(self):
        values = _load_values()
        assert values["seeder"]["activeDeadlineSeconds"] == 120

    def test_ac5_template_references_values(self):
        raw = _load_template_raw()
        assert ".Values.seeder.backoffLimit" in raw
        assert ".Values.seeder.activeDeadlineSeconds" in raw


# ---------------------------------------------------------------------------
# AC6: Kyverno-compliant securityContext
# ---------------------------------------------------------------------------


class TestAC6SecurityContext:
    """AC6: Seeder has Kyverno-compliant securityContext."""

    def test_ac6_privileged_false(self):
        raw = _load_template_raw()
        assert "privileged: false" in raw

    def test_ac6_run_as_non_root(self):
        raw = _load_template_raw()
        assert "runAsNonRoot: true" in raw

    def test_ac6_no_privilege_escalation(self):
        raw = _load_template_raw()
        assert "allowPrivilegeEscalation: false" in raw

    def test_ac6_drop_all_capabilities(self):
        raw = _load_template_raw()
        assert "- ALL" in raw


# ---------------------------------------------------------------------------
# AC7 + AC8: Profile is configurable via values
# ---------------------------------------------------------------------------


class TestAC7AC8Profile:
    """AC7/AC8: Profile comes from values, default is prod."""

    def test_ac7_default_profile_is_prod(self):
        values = _load_values()
        assert values["seeder"]["profile"] == "prod", (
            "Default seeder profile must be 'prod' (safe bootstrap)"
        )

    def test_ac8_template_uses_values_profile(self):
        raw = _load_template_raw()
        assert ".Values.seeder.profile" in raw, (
            "Template must use .Values.seeder.profile for the --profile arg"
        )


# ---------------------------------------------------------------------------
# AC9: No --reset flag
# ---------------------------------------------------------------------------


class TestAC9NoReset:
    """AC9: Template does not use --reset."""

    def test_ac9_no_reset_in_template(self):
        raw = _load_template_raw()
        # Check command/args section for --reset
        assert "--reset" not in raw, (
            "Seeder template must NOT include --reset"
        )


# ---------------------------------------------------------------------------
# AC10: Standard K8s labels
# ---------------------------------------------------------------------------


class TestAC10Labels:
    """AC10: Seeder Job has standard K8s labels."""

    def test_ac10_component_label(self):
        raw = _load_template_raw()
        assert "app.kubernetes.io/component: seeder" in raw

    def test_ac10_part_of_label(self):
        raw = _load_template_raw()
        # Uses the shared labels helper which includes part-of
        assert "control-plane-api.labels" in raw


# ---------------------------------------------------------------------------
# Helm hooks
# ---------------------------------------------------------------------------


class TestHelmHooks:
    """Seeder is a post-install/post-upgrade Helm hook."""

    def test_hook_annotations(self):
        raw = _load_template_raw()
        assert "helm.sh/hook" in raw
        assert "post-install" in raw
        assert "post-upgrade" in raw

    def test_hook_delete_policy(self):
        raw = _load_template_raw()
        assert "helm.sh/hook-delete-policy" in raw
        assert "before-hook-creation" in raw

    def test_conditional_on_enabled(self):
        raw = _load_template_raw()
        assert ".Values.seeder.enabled" in raw


# ---------------------------------------------------------------------------
# RestartPolicy
# ---------------------------------------------------------------------------


class TestRestartPolicy:
    """RestartPolicy must be Never."""

    def test_restart_never(self):
        raw = _load_template_raw()
        assert "restartPolicy: Never" in raw


# ---------------------------------------------------------------------------
# Helm lint
# ---------------------------------------------------------------------------


class TestHelmLint:
    """Chart passes helm lint."""

    def test_helm_lint(self):
        import subprocess

        result = subprocess.run(
            ["helm", "lint", str(CHART_DIR)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"helm lint failed:\n{result.stdout}\n{result.stderr}"
        )
