"""Tests for pushing a loaded image and reading its registry digest."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import push_loaded_image as pli  # noqa: E402

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
PUSH_OK = f"The push refers to repository [ghcr.io/example/portal]\n1.4.0: digest: {DIGEST} size: 1234\n"


def test_parse_image_tags_and_push_digest():
    tags = pli.parse_image_tags(
        "ghcr.io/stoa-platform/portal:1.4.0\n\nghcr.io/stoa-platform/portal:sha-abcd\n"
    )
    assert tags[0] == "ghcr.io/stoa-platform/portal:1.4.0"
    assert pli.digest_from_push_output(PUSH_OK, "ghcr.io/example/portal:1.4.0") == DIGEST
    try:
        pli.digest_from_push_output("pushed\n", "ghcr.io/example/portal:1.4.0")
    except RuntimeError as exc:
        assert "did not report a sha256 digest" in str(exc)
    else:
        raise AssertionError("expected missing digest to fail")
    try:
        pli.parse_image_tags("\n")
    except ValueError:
        pass
    else:
        raise AssertionError("expected empty tags to fail")


def test_push_loaded_image_uses_push_digests_not_inspect():
    tags = "ghcr.io/example/portal:1.4.0\nghcr.io/example/portal:sha-abcd\n"
    calls = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["docker", "push"]:
            tag_name = argv[2].rsplit(":", 1)[1]
            stdout = (
                "The push refers to repository [ghcr.io/example/portal]\n"
                f"{tag_name}: digest: {DIGEST} size: 1234\n"
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        raise AssertionError(f"inspect must not be used: {argv}")

    assert pli.push_loaded_image(tags, runner=runner) == DIGEST
    assert calls[0] == ["docker", "push", "ghcr.io/example/portal:1.4.0"]
    assert calls[1] == ["docker", "push", "ghcr.io/example/portal:sha-abcd"]


def test_digest_from_push_output_rejects_malformed_unrelated_and_wrong_tag():
    bad_outputs = [
        f"1.4.0: digest: {DIGEST}f size: 1234\n",
        f"1.4.0: digest: {DIGEST[:-1]} size: 1234\n",
        f"1.4.0: digest: sha256:{'A' * 64} size: 1234\n",
        f"Layer digest: {DIGEST}\n",
        f"digest: {DIGEST} size: 1234\n",
        f"other-tag: digest: {DIGEST} size: 1234\n",
        f"1.4.0-rc.1: digest: {DIGEST} size: 1234\n",
        f"1.4.0: digest: {DIGEST} size: 1234 trailing\n",
    ]
    for output in bad_outputs:
        try:
            pli.digest_from_push_output(output, "ghcr.io/example/portal:1.4.0")
        except RuntimeError as exc:
            assert "did not report a sha256 digest" in str(exc)
        else:
            raise AssertionError(f"expected rejection for output: {output!r}")


def test_push_loaded_image_rejects_reused_first_tag_summary():
    tags = "ghcr.io/example/portal:1.4.0\nghcr.io/example/portal:sha-abcd\n"

    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout=PUSH_OK, stderr="")

    try:
        pli.push_loaded_image(tags, runner=runner)
    except RuntimeError as exc:
        assert "ghcr.io/example/portal:sha-abcd did not report a sha256 digest" in str(exc)
    else:
        raise AssertionError("expected wrong-tag summary to fail")


def test_push_loaded_image_rejects_divergent_tag_digests():
    tags = "ghcr.io/example/portal:1.4.0\nghcr.io/example/portal:sha-abcd\n"

    def runner(argv, **kwargs):
        if argv[-1].endswith(":1.4.0"):
            return SimpleNamespace(returncode=0, stdout=PUSH_OK, stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=f"sha-abcd: digest: {OTHER} size: 99\n",
            stderr="",
        )

    try:
        pli.push_loaded_image(tags, runner=runner)
    except RuntimeError as exc:
        assert "divergent digests" in str(exc)
    else:
        raise AssertionError("expected divergent digests to fail")


def test_cli_writes_digest(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("IMAGE_TAGS", "ghcr.io/example/portal:1.4.0")

    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout=PUSH_OK, stderr="")

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


def test_cli_rejects_missing_push_digest(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("IMAGE_TAGS", "ghcr.io/example/portal:1.4.0")

    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="pushed\n", stderr="")

    monkeypatch.setattr(pli, "default_runner", runner)
    assert pli.main([]) == 1
    assert not output.exists()
