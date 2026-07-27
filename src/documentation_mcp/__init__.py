from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

from .config import load_settings


__version__ = "0.1.0a1"


def _reconfigure_stdio(stream: Any) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


_reconfigure_stdio(sys.stdin)
_reconfigure_stdio(sys.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="documentation-mcp",
        description="Read-only MCP server for structured Markdown documentation.",
    )
    parser.add_argument("--config", required=True, help="Path to the server TOML configuration")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))
    settings = load_settings(args.config)

    from . import server

    server.configure(settings)
    asyncio.run(server.run())


__all__ = ["__version__", "main"]
