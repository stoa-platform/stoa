"""Tests for pushing a loaded image and reading its registry digest."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import push_loaded_image as pli  # noqa: E402

DIGEST = "sha256:" + "a" * 64


def test_parse_image_tags_and_digest():
    tags = pli.parse_image_tags("ghcr.io/stoa-platform/portal:1.4.0\n\nghcr.io/stoa-platform/portal:sha-abcd\n")
    assert tags[0] == "ghcr.io/stoa-platform/portal:1.4.0"
    assert pli.digest_from_repo_digests(
        [f"ghcr.io/stoa-platform/portal@{DIGEST}"]
    ) == DIGEST
    with pytest.raises(ValueError):
        pli.digest_from_repo_digests(["ghcr.io/stoa-platform/portal:1.4.0"])
    with pytest.raises(ValueError):
        pli.parse_image_tags("\n")


def test_push_loaded_image_pushes_each_tag_then_reads_digest():
    tags = "ghcr.io/example/portal:1.4.0\nghcr.io/example/portal:sha-abcd\n"
    calls = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["docker", "push"]:
            return SimpleNamespace(returncode=0, stdout="pushed\n", stderr="")
        if argv[:3] == ["docker", "inspect", "--format"]:
            return SimpleNamespace(
                returncode=0,
                stdout=f'["ghcr.io/example/portal@{DIGEST}"]\n',
                stderr="",
            )
        raise AssertionError(argv)

    assert pli.push_loaded_image(tags, runner=runner) == DIGEST
    assert calls[0] == ["docker", "push", "ghcr.io/example/portal:1.4.0"]
    assert calls[1] == ["docker", "push", "ghcr.io/example/portal:sha-abcd"]


def test_cli_writes_digest(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("IMAGE_TAGS", "ghcr.io/example/portal:1.4.0")

    def runner(argv, **kwargs):
        if argv[:2] == ["docker", "push"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=f'["ghcr.io/example/portal@{DIGEST}"]\n',
            stderr="",
        )

    monkeypatch.setattr(pli, "default_runner", runner)
    assert pli.main([]) == 0
    assert output.read_text() == f"digest={DIGEST}\n"


def test_cli_rejects_failed_push(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("IMAGE_TAGS", "ghcr.io/example/portal:1.4.0")

    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="denied")

    monkeypatch.setattr(pli, "default_runner", runner)
    assert pli.main([]) == 1
    assert not output.exists()
