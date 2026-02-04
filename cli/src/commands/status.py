"""stoa status — show platform connection and health."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table

from ..client import StoaClient
from ..config import load_config, load_credentials

console = Console()


def status() -> None:
    """Show connection status, auth state, and platform health."""
    config = load_config()
    creds = load_credentials()

    table = Table(title="STOA Platform Status", show_header=False, show_lines=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    # Server info
    table.add_row("Server", config.server)
    table.add_row("Auth Server", config.auth_server)
    table.add_row("Realm", config.realm)

    # Auth status
    if creds.access_token:
        username = creds.claims.get("preferred_username", "unknown")
        email = creds.claims.get("email", "")
        tenant = creds.claims.get("tenant_id", "")
        if isinstance(tenant, list):
            tenant = tenant[0] if tenant else ""

        remaining = creds.expires_at - time.time()
        if remaining > 0:
            mins = int(remaining // 60)
            token_status = f"[green]valid[/green] ({mins}m remaining)"
        else:
            token_status = "[red]expired[/red]"

        table.add_row("User", f"{username} ({email})")
        table.add_row("Tenant", str(tenant) if tenant else "[dim]not set[/dim]")
        table.add_row("Token", token_status)
    else:
        table.add_row("Auth", "[yellow]not authenticated[/yellow]")

    # API health
    try:
        client = StoaClient(config, creds)
        health = client.health()
        table.add_row("API Health", f"[green]{health.status}[/green]")
        if health.version:
            table.add_row("API Version", health.version)
    except Exception as exc:
        table.add_row("API Health", f"[red]unreachable[/red] ({exc})")

    console.print(table)
