"""CLI generator for canonical ``api.yaml`` files.

Spec §7 (CAB-2185 B-FLOW test scaffolding).

Usage::

    python -m src.services.catalog.write_api_yaml \\
      --tenant demo-gitops \\
      --name manual-test \\
      --version 1.0.0 \\
      --backend http://mock-backend:9090 \\
      --output /tmp/api.yaml

Constraints (strictly enforced):

* This tool ONLY generates a YAML file locally.
* It does NOT write to the database.
* It does NOT call Git or any HTTP service.
* It does NOT touch ``api_catalog``.

It is a pure generator, not a mini-writer. Tests in
``tests/services/test_phase4_1_invariants.py`` enforce these constraints
statically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# ``gitops_writer.paths`` is itself a pure module (no DB, no Git, no async).
# Importing only ``is_uuid_shaped`` keeps the helper free of any writer side
# effect while removing the regex duplication. The invariants test still
# pins the helper against the SQLAlchemy / catalog_git_client / github_service
# surfaces.
from src.services.gitops_writer.paths import is_uuid_shaped


def render_api_yaml(
    *,
    tenant_id: str,
    api_name: str,
    version: str,
    backend_url: str,
    display_name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Render the canonical ``api.yaml`` content per spec §6.9 mapping.

    Format frozen by observation of ``payment-api/api.yaml`` (2026-04-26):

    * ``id``, ``name``, ``display_name``, ``version``
    * ``description`` (multiline if provided)
    * ``backend_url`` (single-backend)
    * ``status: active`` (constant for this cycle)
    * ``deployments: {dev: true, staging: false}`` (default for this cycle)
    * Optional: ``category``, ``tags``

    Refuses ``api_name`` UUID-shaped (CAB-2187 B10).

    Args:
        tenant_id: Slug; used only for error messages, NOT included in YAML
            (the YAML is layout-agnostic; tenant ownership is encoded in
            the canonical path ``tenants/{tenant_id}/apis/{api_name}/api.yaml``).
    """
    if is_uuid_shaped(api_name):
        raise ValueError(f"api_name UUID-shaped not allowed: {api_name!r}. Spec §6.4 (CAB-2187 B10).")
    if not api_name:
        raise ValueError("api_name must be non-empty")
    if not tenant_id:
        raise ValueError("tenant_id must be non-empty")
    if not version:
        raise ValueError("version must be non-empty")
    if not backend_url:
        raise ValueError("backend_url must be non-empty")

    data: dict[str, object] = {
        "id": api_name,
        "name": api_name,
        "display_name": display_name or api_name,
        "version": version,
        "backend_url": backend_url,
        "status": "active",
        "deployments": {"dev": True, "staging": False},
    }
    if description:
        data["description"] = description
    if category:
        data["category"] = category
    if tags:
        data["tags"] = list(tags)

    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)


def _resolve_output_path(raw: str) -> Path:
    """Resolve ``--output`` against CWD and refuse symlink/special targets.

    The CLI is a dev scaffold but is sometimes piped into shell scripts that
    interpolate untrusted strings. Refusing symlinks and non-regular files
    keeps the surface obvious: we only ever write a regular file at the
    final path, never follow a symlink that escapes elsewhere.

    Order matters: check ``is_symlink()`` on the unresolved path *before*
    calling :meth:`Path.resolve` (which canonicalises symlinks away).
    """
    raw_path = Path(raw).expanduser()
    # Probe the path as given so symlinks are detected before resolution.
    if raw_path.is_symlink():
        raise ValueError(f"--output target is a symlink (refusing to follow): {raw_path}")
    output = raw_path.resolve()
    if output.exists() and not output.is_file():
        raise ValueError(f"--output target exists and is not a regular file: {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate canonical api.yaml")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--category", default=None)
    parser.add_argument("--tag", action="append", default=None, dest="tags")
    parser.add_argument("--output", required=True)

    args = parser.parse_args(argv)

    try:
        output = _resolve_output_path(args.output)
        yaml_content = render_api_yaml(
            tenant_id=args.tenant,
            api_name=args.name,
            version=args.version,
            backend_url=args.backend,
            display_name=args.display_name,
            description=args.description,
            category=args.category,
            tags=args.tags,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output.write_text(yaml_content)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
