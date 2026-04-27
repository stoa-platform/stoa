"""Regression test for CAB-2179.

Hand-authored UAC fixtures must not carry `spec_hash`. The field is a runtime
drift signal owned by cp-api / DB columns (`BackendApi.spec_hash`,
`Deployment.spec_hash`, `GeneratedTool.spec_hash`); embedding it in
source-tracked fixtures produces a stale, unreproducible value.

The legacy `specs/uac/demo-httpbin.uac.json` carried a 64-char hash that no
visible algorithm reproduced — `_compute_spec_hash` truncates to 16 chars
(see `control-plane-api/src/services/uac_transformer.py:238`).
"""

import json
from pathlib import Path

import pytest

from src.schemas.uac import UacContractSpec


@pytest.fixture
def fixture_paths() -> list[Path]:
    repo_root = Path(__file__).parent.parent.parent
    uac_dir = repo_root / "specs" / "uac"
    if not uac_dir.exists():
        pytest.skip("specs/uac/ not present (cross-tree test)")
    paths = [uac_dir / "demo-httpbin.uac.json"]
    paths.extend(sorted((uac_dir / "examples").glob("*.uac.json")))
    return [p for p in paths if p.exists()]


def test_regression_cab_2179_fixtures_validate(fixture_paths: list[Path]):
    assert fixture_paths, "no UAC fixtures discovered"
    for path in fixture_paths:
        data = json.loads(path.read_text())
        UacContractSpec.model_validate(data)


def test_regression_cab_2179_demo_uac_no_spec_hash(fixture_paths: list[Path]):
    assert fixture_paths, "no UAC fixtures discovered"
    offenders = [
        p.name for p in fixture_paths if "spec_hash" in json.loads(p.read_text())
    ]
    assert offenders == [], (
        f"hand-authored fixtures must not carry spec_hash (runtime field): {offenders}"
    )
