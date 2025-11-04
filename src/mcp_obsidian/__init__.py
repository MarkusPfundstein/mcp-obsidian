import asyncio
import logging
import sys

from . import server

def main():
    """Main entry point for the package."""
    logger = logging.getLogger("mcp-obsidian")
    try:
        asyncio.run(server.main(sys.argv[1:]))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")

# Optionally expose other important items at package level
__all__ = ['main', 'server']
