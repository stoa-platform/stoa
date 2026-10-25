"""Render contracts in the existing API CI job (Helm must be available)."""

import secrets
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/stoa-platform"


def render(*arguments):
    return subprocess.run(
        ["helm", "template", "installation", str(CHART), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def objects(result):
    assert result.returncode == 0, "Helm rendering failed; inspect the local render log"
    return [obj for obj in yaml.safe_load_all(result.stdout) if obj]


def test_default_does_not_render_first_admin_job():
    manifests = objects(render())
    assert not any(obj["kind"] == "Job" and obj["metadata"]["name"] == "stoa-first-admin" for obj in manifests)
    signup = next(obj for obj in manifests if obj["metadata"]["name"] == "stoa-signup-settings")
    assert signup["data"]["SIGNUP_MODE"] == "invite"


@pytest.mark.parametrize("overlay", ["values-dev.yaml", "values-staging.yaml", "values-prod.yaml"])
def test_environment_values_render(overlay):
    objects(render("-f", str(CHART / overlay)))


def test_first_admin_enabled_requires_existing_secret():
    result = render("--set", "stoa.bootstrap.firstAdmin.enabled=true")
    assert result.returncode != 0
    assert "stoa.bootstrap.firstAdmin.existingSecret is required" in result.stderr


def test_first_admin_render_hardening():
    manifests = objects(
        render(
            "--set",
            "stoa.bootstrap.firstAdmin.enabled=true",
            "--set",
            "stoa.bootstrap.firstAdmin.existingSecret=first-admin-input",
        )
    )
    job = next(obj for obj in manifests if obj["kind"] == "Job" and obj["metadata"]["name"] == "stoa-first-admin")
    pod = job["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    container = pod["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert pod["volumes"][1]["secret"]["secretName"] == "first-admin-input"
    assert all("PASSWORD" not in entry["name"] for entry in container["env"])


def test_bootstrap_requires_secret_and_refuses_inline_password(tmp_path):
    result = render("--set", "stoa.bootstrap.enabled=true")
    assert result.returncode != 0
    assert "stoa.bootstrap.keycloak.existingSecret is required" in result.stderr
    token = secrets.token_urlsafe(32)
    values = tmp_path / "private-values.yaml"
    values.touch(mode=0o600)
    values.write_text(
        yaml.safe_dump(
            {
                "stoa": {
                    "bootstrap": {
                        "enabled": True,
                        "keycloak": {"existingSecret": "bootstrap-auth", "adminPassword": token},
                    }
                }
            }
        )
    )
    result = render("-f", str(values))
    assert result.returncode != 0
    assert "Inline bootstrap admin passwords are unsupported" in result.stderr
    assert token not in result.stdout + result.stderr


def test_bootstrap_render_references_secret():
    manifests = objects(
        render(
            "--set",
            "stoa.bootstrap.enabled=true",
            "--set",
            "stoa.bootstrap.keycloak.existingSecret=bootstrap-auth",
        )
    )
    job = next(obj for obj in manifests if obj["kind"] == "Job" and obj["metadata"]["name"] == "stoa-bootstrap")
    container = job["spec"]["template"]["spec"]["containers"][0]
    password = next(env for env in container["env"] if env["name"] == "KC_ADMIN_PASSWORD")
    assert "value" not in password
    assert password["valueFrom"]["secretKeyRef"]["name"] == "bootstrap-auth"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
