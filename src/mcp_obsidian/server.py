import json
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any
import os
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

load_dotenv()

from . import tools

# Load environment variables

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-obsidian")

# Add debug file logging if enabled
debug_log_path = os.getenv("OBSIDIAN_DEBUG_LOG")
if debug_log_path:
    file_handler = logging.FileHandler(debug_log_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
    logger.debug(f"Debug logging enabled, writing to: {debug_log_path}")
    logger.debug(f"Working directory: {os.getcwd()}")
    logger.debug(f"Environment: OBSIDIAN_HOST={os.getenv('OBSIDIAN_HOST')}, OBSIDIAN_PORT={os.getenv('OBSIDIAN_PORT')}, OBSIDIAN_PROTOCOL={os.getenv('OBSIDIAN_PROTOCOL')}")
    logger.debug(f"SSL Config: OBSIDIAN_SSL_CERT_PATH={os.getenv('OBSIDIAN_SSL_CERT_PATH')}, OBSIDIAN_SSL_CERT_BASE64={'set' if os.getenv('OBSIDIAN_SSL_CERT_BASE64') else 'not set'}")
    logger.debug(f"Feature flags: OBSIDIAN_ENABLE_JOURNALING={os.getenv('OBSIDIAN_ENABLE_JOURNALING')!r}, OBSIDIAN_DISABLE_SIMPLE_SEARCH={os.getenv('OBSIDIAN_DISABLE_SIMPLE_SEARCH')!r}")

api_key = os.getenv("OBSIDIAN_API_KEY")
if not api_key:
    logger.error(f"OBSIDIAN_API_KEY environment variable required. Working directory: {os.getcwd()}")
    raise ValueError(f"OBSIDIAN_API_KEY environment variable required. Working directory: {os.getcwd()}")

app = Server("mcp-obsidian")

tool_handlers = {}
def add_tool_handler(tool_class: tools.ToolHandler):
    global tool_handlers

    tool_handlers[tool_class.name] = tool_class

def get_tool_handler(name: str) -> tools.ToolHandler | None:
    if name not in tool_handlers:
        return None
    
    return tool_handlers[name]

add_tool_handler(tools.ListFilesInDirToolHandler())
add_tool_handler(tools.ListFilesInVaultToolHandler())
add_tool_handler(tools.GetFileContentsToolHandler())

# Simple search tool can be disabled for large vaults
if os.getenv("OBSIDIAN_DISABLE_SIMPLE_SEARCH") != "true":
    add_tool_handler(tools.SearchToolHandler())
else:
    logger.info("Simple search tool disabled")

add_tool_handler(tools.PatchContentToolHandler())
add_tool_handler(tools.AppendContentToolHandler())
add_tool_handler(tools.PutContentToolHandler())
add_tool_handler(tools.DeleteFileToolHandler())
add_tool_handler(tools.ComplexSearchToolHandler())
add_tool_handler(tools.BatchGetFileContentsToolHandler())
add_tool_handler(tools.PeriodicNotesToolHandler())
add_tool_handler(tools.RecentPeriodicNotesToolHandler())
add_tool_handler(tools.RecentChangesToolHandler())

# Journaling tool is opt-in via environment variable
if os.getenv("OBSIDIAN_ENABLE_JOURNALING") == "true":
    add_tool_handler(tools.JournalEntryToolHandler())
    logger.info("Journaling tool enabled")
else:
    logger.debug(f"Journaling tool disabled (OBSIDIAN_ENABLE_JOURNALING={os.getenv('OBSIDIAN_ENABLE_JOURNALING')!r})")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    logger.debug(f"list_tools called, returning {len(tool_handlers)} tools")
    return [th.get_tool_description() for th in tool_handlers.values()]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for command line run."""

    logger.debug(f"call_tool: name={name}, arguments={json.dumps(arguments) if isinstance(arguments, dict) else arguments}")

    if not isinstance(arguments, dict):
        logger.error(f"call_tool: arguments must be dictionary, got {type(arguments)}")
        raise RuntimeError("arguments must be dictionary")


    tool_handler = get_tool_handler(name)
    if not tool_handler:
        logger.error(f"call_tool: Unknown tool: {name}")
        raise ValueError(f"Unknown tool: {name}")

    try:
        result = tool_handler.run_tool(arguments)
        logger.debug(f"call_tool: {name} completed successfully")
        return result
    except Exception as e:
        logger.error(f"call_tool: {name} failed with error: {str(e)}", exc_info=True)
        raise RuntimeError(f"Caught Exception. Error: {str(e)}")


async def main():

    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
