"""Validate workflow action pins and the existing Dependabot update path."""

import re
import sys
from pathlib import Path

import yaml

SHA_REFERENCE = re.compile(r"[^\s@]+/[^\s@]+@[0-9a-fA-F]{40}")
IMAGE_REFERENCE = re.compile(r"docker://[^\s@]+@sha256:[0-9a-fA-F]{64}")


def references(document):
    """Read only executable job/step references, never examples in run blocks."""
    for job in document.get("jobs", {}).values():
        if "uses" in job:
            yield job["uses"]
        for step in job.get("steps", []):
            if "uses" in step:
                yield step["uses"]


def pinned(reference):
    return isinstance(reference, str) and (
        reference.startswith("./")
        or SHA_REFERENCE.fullmatch(reference) is not None
        or IMAGE_REFERENCE.fullmatch(reference) is not None
    )


def update_path_enabled(document):
    """Require a scheduled, enabled root GitHub Actions update entry."""
    groups = document.get("multi-ecosystem-groups", {})
    for entry in document.get("updates", []):
        if entry.get("package-ecosystem") != "github-actions":
            continue
        directories = entry.get("directories", [entry.get("directory")])
        schedule = entry.get("schedule") or groups.get(
            entry.get("multi-ecosystem-group"), {}
        ).get("schedule", {})
        if (
            "/" in directories
            and schedule.get("interval") in {"daily", "weekly", "monthly", "quarterly", "semiannually", "yearly", "cron"}
            and entry.get("open-pull-requests-limit", 5) > 0
            and groups.get(entry.get("multi-ecosystem-group"), {}).get("open-pull-requests-limit", 5) > 0
        ):
            return True
    return False


def check(root):
    errors = []
    count = 0
    workflows = root / ".github/workflows"
    for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        for reference in references(yaml.safe_load(path.read_text()) or {}):
            count += 1
            if not pinned(reference):
                errors.append(f"{path.relative_to(root)}: unpinned uses: {reference!r}")
    config = yaml.safe_load((root / ".github/dependabot.yml").read_text())
    if not update_path_enabled(config):
        errors.append(".github/dependabot.yml: scheduled GitHub Actions updates must remain enabled")
    return count, errors


def main():
    root = Path(__file__).resolve().parents[3]
    try:
        count, errors = check(root)
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as error:
        print(f"Cannot validate action references: {error}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Checked {count} workflow references; {len(errors)} errors")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
