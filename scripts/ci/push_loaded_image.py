#!/usr/bin/env python3
"""Push a locally loaded and already verified image; export its registry digest."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def parse_image_tags(image_tags: str) -> list[str]:
    tags = [line.strip() for line in image_tags.splitlines() if line.strip()]
    if not tags:
        raise ValueError("IMAGE_TAGS did not contain an image tag")
    return tags


def digest_from_repo_digests(repo_digests: Sequence[str]) -> str:
    for item in repo_digests:
        if not isinstance(item, str) or "@" not in item:
            continue
        digest = item.rsplit("@", 1)[1]
        if DIGEST_RE.fullmatch(digest):
            return digest
    raise ValueError(f"No sha256 digest in RepoDigests: {list(repo_digests)!r}")


def default_runner(argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), check=False, text=True, capture_output=True, **kwargs)


def push_loaded_image(image_tags: str, runner: Runner | None = None) -> str:
    runner = runner or default_runner
    tags = parse_image_tags(image_tags)
    for tag in tags:
        result = runner(["docker", "push", tag])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"docker push {tag} failed ({result.returncode}): {detail}")
    inspect = runner(["docker", "inspect", "--format", "{{json .RepoDigests}}", tags[0]])
    if inspect.returncode != 0:
        detail = (inspect.stderr or inspect.stdout or "").strip()
        raise RuntimeError(f"docker inspect failed ({inspect.returncode}): {detail}")
    try:
        repo_digests = json.loads(inspect.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"docker inspect returned invalid JSON: {inspect.stdout!r}") from exc
    if not isinstance(repo_digests, list):
        raise RuntimeError(f"Unexpected RepoDigests payload: {inspect.stdout!r}")
    return digest_from_repo_digests(repo_digests)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-tags", default=os.environ.get("IMAGE_TAGS", ""))
    args = parser.parse_args(argv)
    try:
        digest = push_loaded_image(args.image_tags)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"digest={digest}\n")
    else:
        print(f"digest={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
