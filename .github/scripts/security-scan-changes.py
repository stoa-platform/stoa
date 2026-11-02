#!/usr/bin/env python3
"""Select security scan build contexts, using the same Git diff as ci-gate."""

import json
import os
import subprocess
from pathlib import Path

COMPONENTS = ("control-plane-api", "portal", "stoa-gateway", "control-plane-ui")
WEB = {"portal", "control-plane-ui"}
COMMON = {
    "LICENSE", "NOTICE", ".dockerignore", "scripts/ci/release_legal.py",
    ".github/workflows/security-scan.yml", ".github/scripts/security-scan-changes.py",
    "scripts/ci/tests/test_security_scan_paths.py",
}


def select_components(event: str, paths: list[str]) -> list[str]:
    if event in {"merge_group", "push", "schedule", "workflow_dispatch"}:
        return list(COMPONENTS)
    if event != "pull_request":
        raise ValueError(f"Unsupported scan event: {event}")
    # Documentation never needs an image, even inside a component build context.
    paths = [p for p in paths if not (
        p.endswith((".md", ".mdx")) or "docs" in Path(p).parts
        or p.startswith(".claude/")
    )]
    return [component for component in COMPONENTS if any(
        p in COMMON or p.startswith(f"{component}/")
        or (component in WEB and (p.startswith("shared/") or p == "tsconfig.base.json"))
        for p in paths
    )]


def main() -> None:
    event = os.environ["EVENT_NAME"]
    paths = []
    if event == "pull_request":
        # NUL delimiters and no rename folding preserve both sides of moves.
        diff = subprocess.run(
            ["git", "diff", "-z", "--no-renames", "--name-only",
             os.environ["BASE_SHA"], os.environ["HEAD_SHA"]],
            check=True, capture_output=True,
        )
        paths = [os.fsdecode(p) for p in diff.stdout.split(b"\0") if p]
    selected = select_components(event, paths)
    matrix = {"component": [
        {"name": c, "path": c, "context": "." if c in WEB else c} for c in selected
    ]}
    outputs = {c: str(c in selected).lower() for c in COMPONENTS}
    outputs.update({"container-scan": str(bool(selected)).lower(),
                    "container-matrix": json.dumps(matrix, separators=(",", ":"))})
    text = "".join(f"{key}={value}\n" for key, value in outputs.items())
    print(text, end="")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(text)


if __name__ == "__main__":
    main()
