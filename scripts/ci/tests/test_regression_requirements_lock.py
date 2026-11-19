"""Regression: the hash-locked install sets must keep up with requirements.txt.

The control-plane-api image and stoa-bench.yml install from hash-locked files
(OpenSSF Scorecard Pinned-Dependencies). requirements.txt stays the source of
truth: a change there without regenerating the locks must fail here, not ship
an image with stale or missing packages.
"""

import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "control-plane-api/requirements.txt"
LOCKS = [
    ROOT / "control-plane-api/requirements-lock.txt",
    ROOT / "control-plane-api/requirements-bench.txt",
]


def requirement_lines(path: Path) -> list[str]:
    text = re.sub(r"\\\n", " ", path.read_text())
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "-"))]


def locked_versions(path: Path) -> dict[str, tuple[str, str]]:
    locked = {}
    for line in requirement_lines(path):
        requirement = Requirement(line.split(" --hash", 1)[0])
        locked[canonicalize_name(requirement.name)] = (str(requirement.specifier), line)
    return locked


@pytest.mark.parametrize("lock", LOCKS, ids=lambda path: path.name)
def test_regression_lock_satisfies_requirements_txt(lock: Path) -> None:
    locked = locked_versions(lock)
    for line in requirement_lines(SOURCE):
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        assert name in locked, f"{requirement.name} is in requirements.txt but not in {lock.name}"
        version = locked[name][0].removeprefix("==")
        assert requirement.specifier.contains(version, prereleases=True), (
            f"{lock.name} pins {requirement.name}=={version}, outside requirements.txt ({requirement.specifier})"
        )


@pytest.mark.parametrize("lock", LOCKS, ids=lambda path: path.name)
def test_regression_every_locked_package_is_pinned_with_hashes(lock: Path) -> None:
    for specifier, line in locked_versions(lock).values():
        assert specifier.startswith("=="), line
        assert "--hash=sha256:" in line, line


def test_regression_image_installs_from_the_lock() -> None:
    dockerfile = (ROOT / "control-plane-api/Dockerfile").read_text()
    assert "--require-hashes -r requirements-lock.txt" in dockerfile
    assert "-r requirements.txt" not in dockerfile
