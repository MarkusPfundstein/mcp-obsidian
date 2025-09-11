"""Command-line interface for mcp-obsidian.

This module
contains the Typer application and configuration resolution logic. The server
itself is only imported at runtime after environment variables are populated.
"""

from __future__ import annotations

import asyncio

import typer

from .settings import resolve_settings

app = typer.Typer(add_completion=False, help="MCP Obsidian server")


@app.command()
def run(
    vault_path: str | None = typer.Argument(
        None,
        help="Path to vault or plugin config (optional).",
    ),
    protocol: str | None = typer.Option(
        None,
        "--protocol",
        case_sensitive=False,
        help=(
            "Force protocol (http/https). If plugin config enables only one, it is "
            "used."
        ),
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="Override host (default from env or 127.0.0.1)",
    ),
    port: int | None = typer.Option(
        None,
        "--port",
        help="Override port (normally derived from plugin config/protocol).",
    ),
    show_config: bool = typer.Option(
        default=False,
        help="Print resolved configuration then exit",
    ),
) -> None:
    """Run the MCP server with resolved configuration."""
    rs = resolve_settings(vault_path, protocol, host, port)
    if show_config:
        for k, v in rs.as_dict().items():
            typer.echo(f"{k}: {v}")
        raise typer.Exit(code=0)

    # Import server only after environment variables are populated to avoid
    # premature OBSIDIAN_API_KEY validation in transitive imports (tools).
    from . import server  # runtime import after env export

    asyncio.run(server.main())


def main() -> None:  # pragma: no cover - thin wrapper
    """Entry point used by package script definition."""
    app()


__all__ = ["main", "run", "app"]
