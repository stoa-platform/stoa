#!/usr/bin/env python3
"""Resolve the application version injected into a component image build."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

VERSIONED_SERVICES = ("control-plane-api", "control-plane-ui", "portal")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[0-9A-Za-z.-]*)?$")


def version_from_tag(tag: str, service: str) -> str | None:
    """Return X.Y.Z when tag is '<service>-vX.Y.Z', otherwise None."""
    if not tag or not service:
        return None
    prefix = f"{service}-v"
    if not tag.startswith(prefix):
        return None
    version = tag[len(prefix):]
    if not version or not _SEMVER.fullmatch(version):
        return None
    return version


def version_from_source(repo_root: Path, service: str) -> str:
    """Read the Release Please-managed version file for a component."""
    if service == "control-plane-api":
        path = repo_root / "control-plane-api" / "pyproject.toml"
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        version = data.get("project", {}).get("version")
    elif service in ("control-plane-ui", "portal"):
        path = repo_root / service / "package.json"
        version = json.loads(path.read_text(encoding="utf-8")).get("version")
    else:
        raise ValueError(f"No version file mapping for service {service!r}")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"Missing version in {path}")
    version = version.strip()
    if not _SEMVER.fullmatch(version):
        raise ValueError(f"Invalid version {version!r} in {path}")
    return version


def resolve_app_version(
    service: str,
    tag: str,
    repo_root: Path,
    event_name: str = "",
) -> tuple[str, bool]:
    """Return (version, should_verify).

    Versioned services always verify. A component release tag is used only
    for the GitHub `release` event. workflow_dispatch and workflow_call
    always read the checked-out version file, even if the ref name looks
    like a component tag.
    """
    if service not in VERSIONED_SERVICES:
        return "", False
    if event_name == "release":
        tagged = version_from_tag(tag, service)
        if tagged is not None:
            return tagged, True
        if tag and tag.startswith(f"{service}-v"):
            raise ValueError(
                f"Invalid component release tag {tag!r} for service {service!r}"
            )
    return version_from_source(repo_root, service), True


def build_args_for(service: str, version: str) -> str:
    if service not in VERSIONED_SERVICES or not version:
        return ""
    lines = [f"APP_VERSION={version}"]
    if service in ("control-plane-ui", "portal"):
        lines.append(f"VITE_APP_VERSION={version}")
    return "\n".join(lines) + "\n"


def _write_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value:
                handle.write(f"{key}<<EOF\n{value}EOF\n" if value.endswith("\n") else f"{key}<<EOF\n{value}\nEOF\n")
            else:
                handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=os.environ.get("SERVICE", ""))
    parser.add_argument("--tag", default=os.environ.get("TAG", ""))
    parser.add_argument("--event-name", default=os.environ.get("EVENT_NAME", ""))
    parser.add_argument("--repo-root", default=os.environ.get("GITHUB_WORKSPACE", ""))
    args = parser.parse_args(argv)

    if not args.service:
        print("::error::SERVICE is required", file=sys.stderr)
        return 1
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        version, verify = resolve_app_version(
            args.service, args.tag, repo_root, event_name=args.event_name
        )
    except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError, KeyError) as exc:
        print(f"::error::Failed to resolve application version: {exc}", file=sys.stderr)
        return 1

    output = os.environ.get("GITHUB_OUTPUT")
    values = {
        "version": version,
        "verify": "true" if verify else "false",
        "build_args": build_args_for(args.service, version),
    }
    if output:
        _write_output(Path(output), values)
    else:
        for key, value in values.items():
            print(f"{key}={value!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
