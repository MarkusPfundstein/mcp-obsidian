import json
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Optional
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

from .config import get_settings, Settings
from . import tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-obsidian")

# Configuration will be set by CLI or loaded here
config: Optional[Settings] = None

app = Server("mcp-obsidian")

# List of all tool handler classes
handler_classes = [
    tools.ListFilesInDirToolHandler,
    tools.ListFilesInVaultToolHandler,
    tools.GetFileContentsToolHandler,
    tools.SearchToolHandler,
    tools.PatchContentToolHandler,
    tools.AppendContentToolHandler,
    tools.PutContentToolHandler,
    tools.DeleteFileToolHandler,
    tools.ComplexSearchToolHandler,
    tools.BatchGetFileContentsToolHandler,
    tools.PeriodicNotesToolHandler,
    tools.RecentPeriodicNotesToolHandler,
    tools.RecentChangesToolHandler,
]

tool_handlers = {}

def initialize_tool_handlers(config: Settings):
    """Initialize all tool handlers with the given configuration."""
    global tool_handlers
    tool_handlers.clear()
    
    for handler_class in handler_classes:
        handler_instance = handler_class(config)
        tool_handlers[handler_instance.name] = handler_instance

def get_tool_handler(name: str) -> tools.ToolHandler | None:
    if name not in tool_handlers:
        return None
    
    return tool_handlers[name]

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""

    return [th.get_tool_description() for th in tool_handlers.values()]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for command line run."""
    
    if not isinstance(arguments, dict):
        raise RuntimeError("arguments must be dictionary")


    tool_handler = get_tool_handler(name)
    if not tool_handler:
        raise ValueError(f"Unknown tool: {name}")

    try:
        return tool_handler.run_tool(arguments)
    except Exception as e:
        logger.error(str(e))
        raise RuntimeError(f"Caught Exception. Error: {str(e)}")


async def main():
    global config
    
    # Load config if not already set by CLI
    if config is None:
        config = get_settings()
    
    # Initialize tool handlers with the config
    initialize_tool_handlers(config)
    
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
