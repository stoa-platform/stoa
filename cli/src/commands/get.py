"""stoa get — retrieve resources from the platform."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..client import StoaClient
from ..config import load_config, load_credentials

console = Console()

app = typer.Typer(help="Get platform resources.")


@app.command("apis")
def get_apis(
    tenant: str | None = typer.Option(
        None, "--tenant", "-t", help="Tenant ID (default: from token)"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="Output format: table, json, wide"
    ),
) -> None:
    """List all APIs for the current tenant."""
    config = load_config()
    creds = load_credentials()
    client = StoaClient(config, creds)

    try:
        apis = client.list_apis(tenant_id=tenant)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed to fetch APIs:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not apis:
        console.print("[yellow]No APIs found.[/yellow]")
        return

    if output == "json":
        import json

        console.print_json(json.dumps([a.model_dump() for a in apis], default=str))
        return

    table = Table(title="APIs", show_lines=False)
    table.add_column("Name", style="bold cyan")
    table.add_column("Display Name")
    table.add_column("Version")
    table.add_column("Status")
    if output == "wide":
        table.add_column("Backend URL")
        table.add_column("Tags")
        table.add_column("Description")

    for api in apis:
        status_style = "green" if api.status == "active" else "yellow"
        row = [
            api.name,
            api.display_name,
            api.version,
            f"[{status_style}]{api.status}[/{status_style}]",
        ]
        if output == "wide":
            row.extend([
                api.backend_url,
                ", ".join(api.tags),
                api.description[:50] + ("..." if len(api.description) > 50 else ""),
            ])
        table.add_row(*row)

    console.print(table)
    console.print(f"[dim]{len(apis)} API(s) found[/dim]")


@app.command("api")
def get_api(
    name: str = typer.Argument(help="API name or ID"),
    tenant: str | None = typer.Option(
        None, "--tenant", "-t", help="Tenant ID (default: from token)"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="Output format: table, json"
    ),
) -> None:
    """Get details of a specific API by name or ID."""
    config = load_config()
    creds = load_credentials()
    client = StoaClient(config, creds)

    try:
        api = client.get_api(name, tenant_id=tenant)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed to fetch API:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "json":
        import json

        console.print_json(json.dumps(api.model_dump(), default=str))
        return

    table = Table(title=f"API: {api.display_name}", show_header=False, show_lines=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    status_style = "green" if api.status == "active" else "yellow"
    table.add_row("Name", api.name)
    table.add_row("Display Name", api.display_name)
    table.add_row("ID", api.id)
    table.add_row("Version", api.version)
    table.add_row("Status", f"[{status_style}]{api.status}[/{status_style}]")
    table.add_row("Backend URL", api.backend_url)
    table.add_row("Description", api.description or "-")
    table.add_row("Tags", ", ".join(api.tags) if api.tags else "-")
    if api.created_at:
        table.add_row("Created", api.created_at)
    if api.updated_at:
        table.add_row("Updated", api.updated_at)

    console.print(table)
