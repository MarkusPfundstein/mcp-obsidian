from . import server
import asyncio
import sys

def main():
    """Main entry point for the package."""
    asyncio.run(server.main(sys.argv[1:]))

# Optionally expose other important items at package level
__all__ = ['main', 'server']