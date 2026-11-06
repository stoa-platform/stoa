"""Regression tests for CAB-2169: honor the selected deployment environment."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _load_workflow(text: str) -> dict:
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict), "workflow root must be a mapping"
    return loaded


def _control_plane_target(value: str, selected: str | None) -> str:
    """Evaluate the string/boolean fragment used by target fields, without calls."""
    if not value.startswith("${{"):
        return value
    expression = (
        value[3:-2]
        .strip()
        .replace("github.event.inputs.environment", "selected_environment")
        .replace("&&", " and ")
        .replace("||", " or ")
    )
    parsed = ast.parse(expression, mode="eval")
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Compare,
        ast.Eq,
        ast.Name,
        ast.Load,
        ast.Constant,
    )
    assert all(isinstance(node, allowed) for node in ast.walk(parsed))
    assert all(
        node.id == "selected_environment" for node in ast.walk(parsed) if isinstance(node, ast.Name)
    )
    # Selected values are only dev/prod/empty, so Python and Actions truthiness agree.
    return eval(
        compile(parsed, "<target-expression>", "eval"),
        {"__builtins__": {}},
        {"selected_environment": selected},
    )


@pytest.mark.parametrize(
    ("selected", "expected_environment", "expected_url", "expected_verify_endpoint"),
    [
        (None, "dev", "https://dev-api.gostoa.dev", ""),  # push or absent input
        ("", "dev", "https://dev-api.gostoa.dev", ""),
        ("dev", "dev", "https://dev-api.gostoa.dev", ""),
        ("prod", "prod", "https://api.gostoa.dev", "https://api.gostoa.dev/health"),
    ],
)
def test_control_plane_api_environment_is_consistent(
    selected: str | None,
    expected_environment: str,
    expected_url: str,
    expected_verify_endpoint: str,
) -> None:
    workflow = _load_workflow((ROOT / ".github/workflows/control-plane-api-ci.yml").read_text())
    jobs = workflow["jobs"]
    for job in ("docker", "deploy", "smoke-test", "notify"):
        assert (
            _control_plane_target(jobs[job]["with"]["environment"], selected)
            == expected_environment
        ), job
    deploy = jobs["deploy"]["with"]
    assert _control_plane_target(deploy["environment-url"], selected) == expected_url
    # CAB-2084: dev has no health endpoint; production verification stays required.
    assert _control_plane_target(deploy["verify-endpoint"], selected) == expected_verify_endpoint


def test_control_plane_api_environment_choices_remain_explicit() -> None:
    workflow = _load_workflow((ROOT / ".github/workflows/control-plane-api-ci.yml").read_text())
    triggers = workflow.get(True, workflow.get("on"))
    environment = triggers["workflow_dispatch"]["inputs"]["environment"]
    assert environment["type"] == "choice"
    assert environment["default"] == "dev"
    assert environment["options"] == ["dev", "prod"]
    assert triggers["push"]["branches"] == ["main"]


def test_control_plane_api_environment_safety_boundary_is_unchanged() -> None:
    caller = _load_workflow((ROOT / ".github/workflows/control-plane-api-ci.yml").read_text())[
        "jobs"
    ]
    reusable = _load_workflow((ROOT / ".github/workflows/reusable-gitops-deploy.yml").read_text())[
        "jobs"
    ]["gitops-deploy"]
    assert (
        caller["deploy"]["if"]
        == "github.event_name == 'push' || github.event_name == 'workflow_dispatch'"
    )
    assert caller["smoke-test"]["if"] == (
        "(github.event_name == 'push' || github.event_name == 'workflow_dispatch') "
        "&& needs.deploy.result == 'success' && vars.GITOPS_DEPLOY_ENABLED == 'true' "
        "&& github.event.inputs.environment == 'prod'"
    )
    assert caller["deploy"]["with"]["image-tag"] == "${{ needs.docker.outputs.image-tag }}"
    assert reusable["if"] == "vars.GITOPS_DEPLOY_ENABLED == 'true'"
    assert reusable["permissions"] == {"contents": "read"}
    dispatch = next(
        step for step in reusable["steps"] if "repository-dispatch@" in step.get("uses", "")
    )
    assert dispatch["with"]["repository"] == "PotoMitan/stoa-infra"
    assert dispatch["with"]["event-type"] == "image-updated"
    assert dispatch["with"]["token"] == "${{ secrets.STOA_INFRA_DISPATCH_TOKEN }}"
