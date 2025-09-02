"""Command-line interface for mcp-obsidian using Typer."""
import asyncio
import sys
from typing import Optional
import typer
from typing_extensions import Annotated

from .config import Settings
from . import server
from . import __version__


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"mcp-obsidian version: {__version__}")
        raise typer.Exit()


def main(
    # Connection settings
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key",
            envvar="OBSIDIAN_API_KEY",
            help="Obsidian REST API key (required)",
            show_default=False,
        ),
    ] = None,
    host: Annotated[
        Optional[str],
        typer.Option(
            "--host",
            envvar="OBSIDIAN_HOST",
            help="Obsidian host",
            show_default="127.0.0.1",
        ),
    ] = None,
    port: Annotated[
        Optional[int],
        typer.Option(
            "--port",
            envvar="OBSIDIAN_PORT",
            help="Obsidian port",
            show_default="27124",
        ),
    ] = None,
    protocol: Annotated[
        Optional[str],
        typer.Option(
            "--protocol",
            envvar="OBSIDIAN_PROTOCOL",
            help="Protocol (http or https)",
            show_default="https",
        ),
    ] = None,
    # Timeout settings
    connect_timeout: Annotated[
        Optional[int],
        typer.Option(
            "--connect-timeout",
            envvar="OBSIDIAN_CONNECT_TIMEOUT",
            help="Connection timeout in seconds",
            min=1,
            max=60,
            show_default="3",
        ),
    ] = None,
    read_timeout: Annotated[
        Optional[int],
        typer.Option(
            "--read-timeout",
            envvar="OBSIDIAN_READ_TIMEOUT",
            help="Read timeout in seconds",
            min=1,
            max=300,
            show_default="6",
        ),
    ] = None,
    # SSL settings
    verify_ssl: Annotated[
        Optional[bool],
        typer.Option(
            "--verify-ssl/--no-verify-ssl",
            envvar="OBSIDIAN_VERIFY_SSL",
            help="Verify SSL certificates",
            show_default="false",
        ),
    ] = None,
    # Debugging
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose logging",
        ),
    ] = False,
    # Version
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
    # Config check
    config_check: Annotated[
        bool,
        typer.Option(
            "--config-check",
            help="Check and display the current configuration, then exit",
        ),
    ] = False,
):
    """MCP server for Obsidian integration via Local REST API.
    
    The server communicates via stdio with the MCP client (e.g., Claude Desktop).
    Configuration can be provided via environment variables, .env file, or CLI arguments.
    CLI arguments take precedence over environment variables.
    """
    import logging
    
    # Configure logging
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.debug("Verbose logging enabled")
    else:
        logging.basicConfig(level=logging.INFO)
    
    try:
        # Build kwargs dict with only non-None values using dict comprehension
        # Typer has already handled CLI args > env vars for its parameters
        settings_kwargs = {
            key: val for key, val in [
                ("obsidian_api_key", api_key),
                ("obsidian_host", host),
                ("obsidian_port", port),
                ("obsidian_protocol", protocol),
                ("obsidian_connect_timeout", connect_timeout),
                ("obsidian_read_timeout", read_timeout),
                ("obsidian_verify_ssl", verify_ssl),
            ] if val is not None
        }
        
        # Create Settings instance
        # Thanks to settings_customise_sources, values passed to __init__ (CLI args)
        # take precedence over env vars and .env file
        config = Settings(**settings_kwargs)
        
        if verbose:
            logging.debug(f"Settings created with CLI overrides: {settings_kwargs}")
        
        # If config-check requested, display config and exit
        if config_check:
            typer.echo("Current configuration:")
            typer.echo(f"  API Key: {'***' + config.obsidian_api_key[-4:] if len(config.obsidian_api_key) > 4 else '***'}")
            typer.echo(f"  Host: {config.obsidian_host}")
            typer.echo(f"  Port: {config.obsidian_port}")
            typer.echo(f"  Protocol: {config.obsidian_protocol}")
            typer.echo(f"  Base URL: {config.base_url}")
            typer.echo(f"  Connect Timeout: {config.obsidian_connect_timeout}s")
            typer.echo(f"  Read Timeout: {config.obsidian_read_timeout}s")
            typer.echo(f"  Verify SSL: {config.obsidian_verify_ssl}")
            typer.echo("\n✓ Configuration is valid")
            return  # Just return instead of raising Exit
        
        # Replace the global config in server module
        server.config = config
        
        if verbose:
            logging.debug(f"Configuration loaded: host={config.obsidian_host}, port={config.obsidian_port}")
        
        # Run the server
        asyncio.run(server.main())
        
    except ValueError as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Server error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)