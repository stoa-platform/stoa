"""Regression: the hash-locked test requirements must install together.

Dependabot moved pytest to 9.0.3 (#3146) while python-tests.txt and
python-shards.txt still pinned pytest-asyncio 0.26.0, which requires
pytest < 9: pip refused the install and the control-plane-api and
stoa-operator test jobs failed before running a test.
"""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS = ROOT / ".github/workflows/requirements"


def pins(path: Path) -> dict[str, tuple[int, ...]]:
    found = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([0-9][0-9.]*)", line)
        if match:
            found[match.group(1).lower()] = tuple(int(part) for part in match.group(2).rstrip(".").split("."))
    return found


@pytest.mark.parametrize("name", ["python-tests.txt", "python-shards.txt"])
def test_regression_pytest_asyncio_matches_pytest_major(name: str) -> None:
    versions = pins(REQUIREMENTS / name)
    if versions["pytest"][0] >= 9:
        assert versions["pytest-asyncio"][0] >= 1, "pytest-asyncio 0.x requires pytest < 9"
        assert "typing-extensions" in versions, "pytest-asyncio 1.x needs typing-extensions on Python < 3.13"


def test_regression_control_plane_api_accepts_pytest_asyncio_1() -> None:
    project = tomllib.loads((ROOT / "control-plane-api/pyproject.toml").read_text())
    dev = project["project"]["optional-dependencies"]["dev"]
    asyncio_pin = next(item for item in dev if item.startswith("pytest-asyncio"))
    assert "<1" not in asyncio_pin.replace(" ", "")
    options = project["tool"]["pytest"]["ini_options"]
    assert options["asyncio_default_fixture_loop_scope"] == "session"
    assert options["asyncio_default_test_loop_scope"] == "session"
