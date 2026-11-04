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
SAST_COMMON = {
    ".github/workflows/ci-gate.yml", "pyproject.toml", ".bandit",
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs",
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    "Cargo.toml", "Cargo.lock", "rust-toolchain", "rust-toolchain.toml",
    "clippy.toml", ".clippy.toml",
}


def web_filters() -> dict[str, list[str]]:
    """Share SAST inputs with paths-filter without duplicating global rules."""
    common = ["shared/**", "tsconfig.base.json", ".cargo/**", *sorted(COMMON | SAST_COMMON)]
    return {component: [
        "{" + ",".join([f"{component}/**", *common]) + "}",
        "!**/*.{md,mdx}", "!.claude/**",
    ] for component in sorted(WEB)}


def select_components(event: str, paths: list[str], *, sast: bool = False) -> list[str]:
    if event in {"merge_group", "push", "schedule", "workflow_dispatch"}:
        return list(COMPONENTS)
    if event != "pull_request":
        raise ValueError(f"Unsupported scan event: {event}")
    # SAST still scans executable files under docs/; prose needs neither scan.
    paths = [p for p in paths if not (
        p.endswith((".md", ".mdx")) or (not sast and "docs" in Path(p).parts)
        or p.startswith(".claude/")
    )]
    return [component for component in COMPONENTS if any(
        p in COMMON or p.startswith(f"{component}/")
        or (sast and (p in SAST_COMMON or p.startswith(".cargo/")))
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
    sast = select_components(event, paths, sast=True)
    matrix = {"component": [
        {"name": c, "path": c, "context": "." if c in WEB else c} for c in selected
    ]}
    outputs = {c: str(c in selected).lower() for c in COMPONENTS}
    outputs.update({"container-scan": str(bool(selected)).lower(),
                    "container-matrix": json.dumps(matrix, separators=(",", ":")),
                    "web-filters": json.dumps(web_filters(), separators=(",", ":")),
                    "sast-rust": str("stoa-gateway" in sast).lower(),
                    "sast-python": str("control-plane-api" in sast).lower(),
                    "sast-javascript": str(bool(WEB.intersection(sast))).lower()})
    text = "".join(f"{key}={value}\n" for key, value in outputs.items())
    print(text, end="")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(text)


if __name__ == "__main__":
    main()
