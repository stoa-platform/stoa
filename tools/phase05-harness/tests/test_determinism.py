"""Determinism + integrity checks for phase05-harness.

These lock the P1 frozen contract. Any intentional change to behavior must
also update the sha256 pins in README.md (and the Decision Gate log).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
sys.path.insert(0, str(ROOT))

from build_enriched import (  # noqa: E402
    build_coarse,
    build_enriched,
    build_per_op,
    generator_sha256,
    spec_sha256,
)


def _load(name: str) -> dict:
    return yaml.safe_load((SPECS / name).read_text())


@pytest.mark.parametrize(
    "spec_name,expected_sha",
    [
        ("banking-services-v1-2.yaml", "79689dfbee7347e2fb00d2f8979058c97a65955560d7552e2ea95e698a4d8249"),  # gitleaks:allow — sha256 spec pin
        ("payment-api.yaml", "144c2daa521e00c413c3ce3d95084a728ba03368391b4d6e4a7053100ca9fe17"),  # gitleaks:allow — sha256 spec pin
        ("fapi-accounts.yaml", "b9822eeed1d24fa1896d636baa062b7a2a29bcec00165b3830049d6222fad5c5"),  # gitleaks:allow — sha256 spec pin
    ],
)
def test_spec_sha256_pinned(spec_name: str, expected_sha: str) -> None:
    actual = spec_sha256(SPECS / spec_name)
    assert actual == expected_sha, f"spec drift: {spec_name} now {actual}"


def test_generator_deterministic() -> None:
    spec = _load("payment-api.yaml")
    a = json.dumps(build_enriched(spec, "t", "a"), sort_keys=True)
    b = json.dumps(build_enriched(spec, "t", "a"), sort_keys=True)
    assert a == b


def test_enriched_has_action_discriminator() -> None:
    spec = _load("payment-api.yaml")
    tool = build_enriched(spec, "t", "payment-api")
    schema = tool["inputSchema"]
    assert set(schema["required"]) == {"action", "params"}
    assert "$defs" in schema
    for op_id, sub in schema["$defs"].items():
        assert sub["properties"]["action"]["const"] == op_id, f"{op_id} missing discriminator"
        assert "action" in sub["required"]
    enum = schema["properties"]["action"]["enum"]
    assert sorted(enum) == enum, "action enum must be sorted"
    assert set(enum) == set(schema["$defs"].keys())


def test_per_op_names_unique_and_sorted() -> None:
    spec = _load("banking-services-v1-2.yaml")
    tools = build_per_op(spec, "demo", "banking-services-v1-2")
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names)), "duplicate tool names"
    assert names == sorted(names), "tools must be sorted for determinism"
    assert len(tools) == 70


def test_coarse_is_opaque() -> None:
    spec = _load("fapi-accounts.yaml")
    tool = build_coarse(spec, "demo", "fapi-accounts")
    schema = tool["inputSchema"]
    assert "$defs" not in schema
    assert "enum" not in schema["properties"]["action"]
    assert schema["properties"]["params"] == {
        "type": "object",
        "description": "operation parameters",
    }


def test_prompt_corpus_counts() -> None:
    prompts = [
        json.loads(l)
        for l in (ROOT / "prompts.jsonl").read_text().splitlines()
        if l.strip()
    ]
    assert len(prompts) >= 90
    apis = {p["api"] for p in prompts}
    assert apis == {"banking-services-v1-2", "payment-api", "fapi-accounts"}
    for api in apis:
        subset = [p for p in prompts if p["api"] == api]
        assert len(subset) >= 30, f"{api}: only {len(subset)} prompts"

    distractor = [p for p in prompts if p["category"] == "distractor"]
    no_valid = [p for p in prompts if p["category"] == "no_valid_tool"]
    assert len(distractor) / len(prompts) >= 0.20
    assert len(no_valid) / len(prompts) >= 0.10


def test_ground_truth_resolves_to_operation_ids() -> None:
    prompts = [
        json.loads(l)
        for l in (ROOT / "prompts.jsonl").read_text().splitlines()
        if l.strip()
    ]
    apis = {p["api"] for p in prompts}
    per_api_ops: dict[str, set[str]] = {}
    for api in apis:
        spec = _load(f"{api}.yaml")
        ops: set[str] = set()
        for _path, item in (spec.get("paths") or {}).items():
            for m, op in (item or {}).items():
                if isinstance(op, dict) and m.lower() in ("get", "post", "put", "patch", "delete"):
                    if op.get("operationId"):
                        ops.add(op["operationId"])
        per_api_ops[api] = ops
    for p in prompts:
        gt_op = p["ground_truth"]["op_id"]
        if gt_op is None:
            continue
        assert gt_op in per_api_ops[p["api"]], (
            f"prompt {p['id']} references non-existent op {gt_op} on {p['api']}"
        )


def test_score_end_to_end_stub_pipeline(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    report = tmp_path / "report.json"

    env_run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run_bench.py"),
            "--prompts", str(ROOT / "prompts.jsonl"),
            "--specs-dir", str(SPECS),
            "--dry-run",
            "--runs", "1",
            "--out", str(runs),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert env_run.returncode == 0, env_run.stderr
    assert runs.exists()

    env_score = subprocess.run(
        [
            sys.executable,
            str(ROOT / "score.py"),
            "--prompts", str(ROOT / "prompts.jsonl"),
            "--runs", str(runs),
            "--out", str(report),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert env_score.returncode == 0, env_score.stderr

    data = json.loads(report.read_text())
    assert "verdicts" in data
    assert set(data["verdicts"].keys()) == {"per-op", "enriched-single"}
    for v in data["verdicts"].values():
        assert v["verdict"] in ("GREEN", "RED")


def test_generator_sha_matches_pin() -> None:
    """If this fails, the generator changed — update README 'Generator pin'."""
    pinned_file = ROOT / ".generator.sha256"
    assert pinned_file.exists(), "Missing .generator.sha256 lock file"
    pinned = pinned_file.read_text().strip()
    actual = generator_sha256()
    assert pinned == actual, (
        f"Generator drift.\n  pinned: {pinned}\n  actual: {actual}\n"
        f"If intentional: update .generator.sha256 AND README 'Generator pin'."
    )
