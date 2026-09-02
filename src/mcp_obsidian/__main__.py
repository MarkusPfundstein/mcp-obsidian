import asyncio
import os
import sys

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Debug output to stderr for troubleshooting
print(f"[mcp-obsidian] OBSIDIAN_API_KEY set: {bool(os.getenv('OBSIDIAN_API_KEY'))}", file=sys.stderr)
print(f"[mcp-obsidian] OBSIDIAN_PROTOCOL={os.getenv('OBSIDIAN_PROTOCOL')}", file=sys.stderr)
print(f"[mcp-obsidian] OBSIDIAN_HOST={os.getenv('OBSIDIAN_HOST')}", file=sys.stderr)
print(f"[mcp-obsidian] OBSIDIAN_PORT={os.getenv('OBSIDIAN_PORT')}", file=sys.stderr)
sys.stderr.flush()

from mcp_obsidian.server import main

if __name__ == "__main__":
    asyncio.run(main())
