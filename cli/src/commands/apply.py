"""stoa apply — create or update resources from YAML manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console

from ..client import StoaClient
from ..config import load_config, load_credentials

console = Console()

SUPPORTED_KINDS = {"API"}


def apply(
    file: Path = typer.Option(
        ..., "--file", "-f", help="Path to YAML manifest", exists=True
    ),
    tenant: str | None = typer.Option(
        None, "--tenant", "-t", help="Tenant ID (default: from token)"
    ),
) -> None:
    """Apply a resource manifest (YAML) to the STOA platform.

    Supports single documents and multi-document YAML (---).

    Example manifest:

        kind: API
        metadata:
          name: weather-api
        spec:
          displayName: Weather API
          version: "1.0.0"
          description: Real-time weather data
          backendUrl: https://api.weather.com/v1
          tags:
            - weather
            - public
    """
    config = load_config()
    creds = load_credentials()
    client = StoaClient(config, creds)

    raw = file.read_text()
    docs = list(yaml.safe_load_all(raw))

    if not docs:
        console.print("[yellow]No documents found in file.[/yellow]")
        raise typer.Exit(code=1)

    applied = 0
    errors = 0

    for doc in docs:
        if doc is None:
            continue
        try:
            _apply_document(client, doc, tenant_id=tenant)
            applied += 1
        except Exception as exc:
            console.print(f"[red]Error applying document:[/red] {exc}")
            errors += 1

    if errors:
        console.print(f"[yellow]Applied {applied}, failed {errors}.[/yellow]")
        raise typer.Exit(code=1)

    console.print(f"[green]{applied} resource(s) applied.[/green]")


def _apply_document(
    client: StoaClient,
    doc: dict[str, Any],
    tenant_id: str | None = None,
) -> None:
    """Apply a single YAML document."""
    kind = doc.get("kind", "").strip()
    if kind not in SUPPORTED_KINDS:
        supported = ", ".join(sorted(SUPPORTED_KINDS))
        raise ValueError(f"Unsupported kind '{kind}'. Supported: {supported}")

    if kind == "API":
        _apply_api(client, doc, tenant_id)


def _apply_api(
    client: StoaClient,
    doc: dict[str, Any],
    tenant_id: str | None = None,
) -> None:
    """Create or update an API from a manifest."""
    metadata = doc.get("metadata", {})
    spec = doc.get("spec", {})
    name = metadata.get("name", "")

    if not name:
        raise ValueError("metadata.name is required")

    payload = {
        "name": name,
        "display_name": spec.get("displayName", name),
        "version": spec.get("version", "1.0.0"),
        "description": spec.get("description", ""),
        "backend_url": spec.get("backendUrl", ""),
        "tags": spec.get("tags", []),
    }
    if spec.get("openapiSpec"):
        payload["openapi_spec"] = spec["openapiSpec"]

    if not payload["backend_url"]:
        raise ValueError("spec.backendUrl is required")

    # Try to find existing API to decide create vs update
    try:
        existing = client.get_api(name, tenant_id=tenant_id)
        client.update_api(existing.id, payload, tenant_id=tenant_id)
        console.print(f"  [blue]updated[/blue] API/{name}")
    except RuntimeError:
        # API not found → create
        client.create_api(payload, tenant_id=tenant_id)
        console.print(f"  [green]created[/green] API/{name}")
