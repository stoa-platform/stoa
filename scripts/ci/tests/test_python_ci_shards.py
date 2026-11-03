"""Exercise the API shard and combined-coverage gates with real pytest runs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/reusable-python-ci.yml").read_text())
JOBS = WORKFLOW["jobs"]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_")}
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def aggregate(cwd: Path) -> subprocess.CompletedProcess[str]:
    step = next(s for s in JOBS["coverage"]["steps"] if s.get("name") == "Combine coverage and enforce threshold")
    # Dependencies are installed by the test workflow; exercise the production gate itself.
    script = "\n".join(line for line in step["run"].splitlines() if "pip install" not in line)
    script = script.replace("${{ inputs.coverage-threshold }}", "70")
    return run(["bash", "-eo", "pipefail", "-c", "COMPONENT=component\n" + script], cwd)


def test_workflow_keeps_shards_and_combined_coverage_required() -> None:
    api = yaml.safe_load((ROOT / ".github/workflows/control-plane-api-ci.yml").read_text())
    assert api["jobs"]["ci"]["with"]["test-shards"] == 2
    assert api["jobs"]["ci"]["with"]["coverage-threshold"] == 70
    assert JOBS["test"]["strategy"]["fail-fast"] is False
    assert JOBS["coverage"]["needs"] == "test"
    assert JOBS["coverage"]["if"] == "always() && inputs.test-shards == 2"
    gate = JOBS["coverage"]["steps"][0]
    for state in ("failure", "cancelled", "skipped", ""):
        proc = subprocess.run(["bash", "-c", gate["run"]], env={**os.environ, "TEST_RESULT": state})
        assert proc.returncode != 0
    assert subprocess.run(["bash", "-c", gate["run"]], env={**os.environ, "TEST_RESULT": "success"}).returncode == 0
    upload = next(s for s in JOBS["test"]["steps"] if s.get("name") == "Upload coverage shard")
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"


def test_real_shards_are_disjoint_complete_and_combined_coverage_is_enforced(tmp_path: Path) -> None:
    project = tmp_path / "component"
    (project / "src").mkdir(parents=True)
    (project / "src/__init__.py").write_text("")
    source = "\n".join(f"def f{i}(flag):\n    a = {i}\n    if flag:\n        return a + 1\n    return a + 3\n" for i in range(8))
    (project / "src/sample.py").write_text(source)
    tests = "from src import sample\nimport pytest\n" + "\n".join(
        f"@pytest.mark.xdist_group('group{i % 2}')\ndef test_{i}():\n    assert sample.f{i}(True) == {i + 1}\n    assert sample.f{i}(False) == {i + 3}\n" for i in range(8)
    )
    (project / "test_sample.py").write_text(tests)
    (project / "pyproject.toml").write_text('[tool.coverage.run]\nsource = ["src"]\nbranch = true\n[tool.coverage.report]\nfail_under = 70\n')
    selected = []
    for shard in (1, 2):
        runner = tmp_path / f"runner-{shard}/component"
        shutil.copytree(project, runner, ignore=shutil.ignore_patterns("coverage-shards"))
        proc = run([sys.executable, "-m", "pytest", "test_sample.py", "-q", "-n", "2", "--dist", "loadgroup",
                    "--splits", "2", "--group", str(shard), "--splitting-algorithm", "least_duration",
                    "--cov=src", "--cov-fail-under=0", f"--junitxml=results-{shard}.xml"], runner)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        # Pytest versions differ in whether JUnit names include xdist's group suffix.
        selected.append({
            c.attrib["name"].partition("@")[0]
            for c in ET.parse(runner / f"results-{shard}.xml").iter("testcase")
        })
        assert run([sys.executable, "-m", "coverage", "report", "--fail-under=70"], runner).returncode != 0
        destination = project / f"coverage-shards/{shard}"
        destination.mkdir(parents=True)
        (runner / ".coverage").rename(destination / f".coverage.shard-{shard}")
    assert selected[0].isdisjoint(selected[1])
    assert selected[0] | selected[1] == {f"test_{i}" for i in range(8)}
    combined = aggregate(project)
    assert combined.returncode == 0, combined.stdout + combined.stderr
    rates = ET.parse(project / "coverage.xml").getroot().attrib
    assert float(rates["line-rate"]) == float(rates["branch-rate"]) == 1

    # New uncovered code must still fail the production aggregate threshold.
    with (project / "src/sample.py").open("a") as target:
        target.write("\n".join(f"uncovered_{i} = {i}" for i in range(100)))
    assert aggregate(project).returncode != 0


@pytest.mark.parametrize("missing", (1, 2))
def test_missing_coverage_shard_fails(tmp_path: Path, missing: int) -> None:
    other = 3 - missing
    directory = tmp_path / f"coverage-shards/{other}"
    directory.mkdir(parents=True)
    (directory / f".coverage.shard-{other}").write_text("not a coverage database")
    assert aggregate(tmp_path).returncode != 0


@pytest.mark.parametrize("invalid_shard", (1, 2))
@pytest.mark.parametrize("invalid_data", ("malformed", "empty-file", "empty-database"))
def test_unusable_coverage_shard_fails(tmp_path: Path, invalid_shard: int, invalid_data: str) -> None:
    source = tmp_path / "src/sample.py"
    source.parent.mkdir()
    source.write_text("answer = 42\n")
    (tmp_path / "pyproject.toml").write_text("[tool.coverage.report]\nfail_under = 70\n")
    for shard in (1, 2):
        path = tmp_path / f"coverage-shards/{shard}/.coverage.shard-{shard}"
        path.parent.mkdir(parents=True)
        if shard == invalid_shard and invalid_data != "empty-database":
            path.write_text("not a coverage database" if invalid_data == "malformed" else "")
        else:
            data = CoverageData(basename=str(path))
            data.add_lines({str(source): set() if shard == invalid_shard else {1}})
            data.write()
            data.close()
    assert aggregate(tmp_path).returncode != 0
