"""STOA CLI — entry point.

Usage:
    stoa login
    stoa logout
    stoa get apis
    stoa get api <name>
    stoa apply -f manifest.yaml
    stoa status
"""

from __future__ import annotations

import typer

from . import __version__
from .commands.apply import apply
from .commands.get import app as get_app
from .commands.login import login, logout
from .commands.status import status

app = typer.Typer(
    name="stoa",
    help="STOA Platform CLI — manage APIs, tenants, and MCP tools.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Top-level commands ──────────────────────────────────────
app.command("login")(login)
app.command("logout")(logout)
app.command("apply")(apply)
app.command("status")(status)

# ── Sub-group: get ──────────────────────────────────────────
app.add_typer(get_app, name="get")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit."
    ),
) -> None:
    """STOA Platform CLI."""
    if version:
        typer.echo(f"stoa {__version__}")
        raise typer.Exit()


def app_runner() -> None:
    """Entry point for pyproject.toml [project.scripts]."""
    app()
