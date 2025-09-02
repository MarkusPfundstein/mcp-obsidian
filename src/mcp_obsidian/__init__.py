from . import server
import asyncio

__version__ = "0.2.1"

def main():
    """Main entry point for the package."""
    # Use CLI as the main entry point
    import typer
    from .cli import main as cli_main
    typer.run(cli_main)

def main_legacy():
    """Legacy entry point that directly runs the server."""
    asyncio.run(server.main())

# Optionally expose other important items at package level
__all__ = ['main', 'main_legacy', 'server', '__version__']