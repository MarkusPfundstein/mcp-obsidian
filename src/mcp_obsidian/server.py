import logging
import os
from collections.abc import Sequence
from typing import Any
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

api_key = os.getenv("OBSIDIAN_API_KEY")
if not api_key:
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
add_tool_handler(tools.SearchToolHandler())
add_tool_handler(tools.PatchContentToolHandler())
add_tool_handler(tools.AppendContentToolHandler())
add_tool_handler(tools.PutContentToolHandler())
add_tool_handler(tools.DeleteFileToolHandler())
add_tool_handler(tools.ComplexSearchToolHandler())
add_tool_handler(tools.BatchGetFileContentsToolHandler())
add_tool_handler(tools.PeriodicNotesToolHandler())
add_tool_handler(tools.RecentPeriodicNotesToolHandler())
add_tool_handler(tools.RecentChangesToolHandler())

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


def _normalize_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


async def _run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


async def _run_sse(
    host: str,
    port: int,
    sse_path: str,
    messages_path: str,
    debug: bool,
) -> None:
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    sse_transport = SseServerTransport(messages_path)

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    async def handle_messages(request):
        await sse_transport.handle_post_message(
            request.scope, request.receive, request._send
        )

    starlette_app = Starlette(
        debug=debug,
        routes=[
            Route(sse_path, endpoint=handle_sse),
            Route(messages_path, endpoint=handle_messages, methods=["POST"]),
        ],
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )
    logger.info(
        "Starting SSE transport on %s:%s (sse=%s, messages=%s)",
        host,
        port,
        sse_path,
        messages_path,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower().strip()

    if transport == "stdio":
        logger.info("Starting MCP server using stdio transport")
        await _run_stdio()
        return

    if transport not in {"sse"}:
        raise ValueError(
            f"Unsupported MCP_TRANSPORT '{transport}'. Expected 'stdio' or 'sse'."
        )

    host = os.getenv("MCP_SSE_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_SSE_PORT", "8000"))
    sse_path = _normalize_path(os.getenv("MCP_SSE_PATH", "/sse"))
    messages_path = _normalize_path(os.getenv("MCP_SSE_MESSAGES_PATH", "/messages"))
    debug = os.getenv("MCP_SSE_DEBUG", "").lower() in {"1", "true", "yes", "on"}

    await _run_sse(host, port, sse_path, messages_path, debug)
