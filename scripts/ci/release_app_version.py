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
DEFAULT_DEV_VERSION = "0.0.0-dev"
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


def version_from_platform_tag(tag: str) -> str | None:
    """Return X.Y.Z when tag is a platform release tag 'vX.Y.Z', otherwise None."""
    if not tag or not tag.startswith("v"):
        return None
    version = tag[1:]
    if not version or not _SEMVER.fullmatch(version):
        return None
    return version


def version_from_source(repo_root: Path, service: str) -> str:
    """Read the Release Please-managed version file for a component.

    Missing, null, or blank version fields fall back to DEFAULT_DEV_VERSION.
    Present non-semver versions still fail closed.
    """
    if service == "control-plane-api":
        path = repo_root / "control-plane-api" / "pyproject.toml"
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project = data.get("project")
        if project is None:
            version = None
        elif isinstance(project, dict):
            version = project.get("version")
        else:
            raise ValueError(f"Invalid [project] section in {path}")
    elif service in ("control-plane-ui", "portal"):
        path = repo_root / service / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid manifest object in {path}")
        version = data.get("version")
    else:
        raise ValueError(f"No version file mapping for service {service!r}")
    if version is None:
        return DEFAULT_DEV_VERSION
    if not isinstance(version, str):
        raise ValueError(f"Invalid version {version!r} in {path}")
    version = version.strip()
    if not version:
        return DEFAULT_DEV_VERSION
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

    Versioned services always verify. On the GitHub `release` event, a
    matching component tag (`<service>-vX.Y.Z`) or platform release tag
    (`vX.Y.Z`) supplies the injected version, and malformed component or
    platform tags fail closed. workflow_dispatch and workflow_call always
    read the checked-out version file (falling back to 0.0.0-dev when
    missing or blank), even if the ref name looks like a release tag.
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
        platform = version_from_platform_tag(tag)
        if platform is not None:
            return platform, True
        if tag and tag.startswith("v"):
            raise ValueError(
                f"Invalid platform release tag {tag!r} for service {service!r}"
            )
    return version_from_source(repo_root, service), True


def build_args_for(service: str, version: str) -> str:
    version = version.strip()
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
