"""stoa login — authenticate via Keycloak OIDC."""

from __future__ import annotations

import typer
from rich.console import Console

from ..auth import login_interactive
from ..config import clear_credentials, load_config, save_config

console = Console()


def login(
    server: str = typer.Option(
        "",
        "--server",
        "-s",
        help="API server URL (e.g. https://api.gostoa.dev)",
    ),
    auth_server: str = typer.Option(
        "",
        "--auth-server",
        help="Keycloak URL (e.g. https://auth.gostoa.dev)",
    ),
) -> None:
    """Authenticate with the STOA platform via browser-based OIDC login."""
    config = load_config()

    if server:
        config.server = server
    if auth_server:
        config.auth_server = auth_server

    save_config(config)

    console.print(f"[bold]Logging in to[/bold] {config.auth_server}")
    console.print("Opening browser for authentication...")

    try:
        creds = login_interactive(config)
    except RuntimeError as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    username = creds.claims.get("preferred_username", "unknown")
    email = creds.claims.get("email", "")
    tenant = creds.claims.get("tenant_id", "")
    if isinstance(tenant, list):
        tenant = tenant[0] if tenant else ""

    if tenant:
        config.tenant_id = str(tenant)
        save_config(config)

    console.print(f"[green]Logged in as[/green] {username} ({email})")
    if tenant:
        console.print(f"[dim]Tenant:[/dim] {tenant}")
    console.print("[dim]Token stored in[/dim] ~/.stoa/credentials.json")


def logout() -> None:
    """Clear stored credentials."""
    clear_credentials()
    console.print("[green]Logged out.[/green] Credentials removed.")
