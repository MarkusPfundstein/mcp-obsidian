import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from typing import Any

from contextlib import asynccontextmanager

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


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP Obsidian server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        help="Transport to use (defaults to MCP_TRANSPORT env var or stdio).",
    )
    parser.add_argument(
        "--http-host",
        dest="http_host",
        help="Host for HTTP transport (defaults to MCP_HTTP_HOST env var or 127.0.0.1).",
    )
    parser.add_argument(
        "--http-port",
        dest="http_port",
        type=int,
        help="Port for HTTP transport (defaults to MCP_HTTP_PORT env var or 8800).",
    )
    parser.add_argument(
        "--http-root-path",
        dest="http_root_path",
        help="Root path for HTTP transport (defaults to MCP_HTTP_ROOT_PATH env var).",
    )
    parser.add_argument(
        "--http-allow-origins",
        dest="http_allow_origins",
        action="append",
        help=(
            "CORS origins to allow when using HTTP transport. "
            "Repeat flag to add multiple origins (defaults to MCP_HTTP_ALLOW_ORIGINS env var)."
        ),
    )
    return parser.parse_args(argv)


def _resolve_http_options(args: argparse.Namespace) -> dict[str, Any]:
    http_host = args.http_host or os.getenv("MCP_HTTP_HOST", "127.0.0.1")
    http_port = args.http_port or int(os.getenv("MCP_HTTP_PORT", "8800"))
    http_root_path = args.http_root_path or os.getenv("MCP_HTTP_ROOT_PATH")

    if args.http_allow_origins is not None:
        http_allow_origins = [origin.strip() for origin in args.http_allow_origins if origin.strip()]
    else:
        origins_env = os.getenv("MCP_HTTP_ALLOW_ORIGINS")
        http_allow_origins = (
            [origin.strip() for origin in origins_env.split(",") if origin.strip()]
            if origins_env
            else None
        )

    return {
        "host": http_host,
        "port": http_port,
        "root_path": http_root_path,
        "allowed_origins": http_allow_origins,
    }


async def _run_stdio_transport() -> None:

    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def _build_cors_middleware(allowed_origins: Sequence[str] | None):
    if not allowed_origins:
        return []

    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware

    return [
        Middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
    ]


async def _run_sse_http_transport(
    *,
    host: str,
    port: int,
    root_path: str | None,
    allowed_origins: Sequence[str] | None,
) -> None:
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Mount, Route
        from mcp.server.sse import SseServerTransport
    except ImportError as exc:
        raise RuntimeError(
            "HTTP transport requested, but required dependencies were not found. "
            "Ensure the 'mcp' package is installed with HTTP support dependencies."
        ) from exc

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        try:
            async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options(),
                )
        except Exception:
            logger.exception("Error while handling SSE connection")
            raise
        return Response()

    middleware = _build_cors_middleware(allowed_origins)

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        middleware=middleware,
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        root_path=root_path or "",
        log_level=logging.getLevelName(logger.getEffectiveLevel()).lower(),
    )
    server = uvicorn.Server(config)

    logger.info("Starting HTTP (SSE) transport on http://%s:%s", host, port)
    await server.serve()


class _StreamableHTTPASGIApp:
    def __init__(self, session_manager):
        self._session_manager = session_manager

    async def __call__(self, scope, receive, send):
        await self._session_manager.handle_request(scope, receive, send)


async def _run_streamable_http_transport(
    *,
    host: str,
    port: int,
    root_path: str | None,
    allowed_origins: Sequence[str] | None,
) -> None:
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    except ImportError as exc:
        raise RuntimeError(
            "Streamable HTTP transport requested, but required dependencies were not found. "
            "Ensure the installed 'mcp' package includes Streamable HTTP support."
        ) from exc

    session_manager = StreamableHTTPSessionManager(app)
    streamable_app = _StreamableHTTPASGIApp(session_manager)

    middleware = _build_cors_middleware(allowed_origins)

    @asynccontextmanager
    async def lifespan(_starlette_app):
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[Route("/mcp", endpoint=streamable_app)],
        middleware=middleware,
        lifespan=lifespan,
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        root_path=root_path or "",
        log_level=logging.getLevelName(logger.getEffectiveLevel()).lower(),
    )
    server = uvicorn.Server(config)

    logger.info("Starting streamable-http transport on http://%s:%s/mcp", host, port)
    await server.serve()


async def _run_http_transport(
    *,
    transport: str,
    host: str,
    port: int,
    root_path: str | None,
    allowed_origins: Sequence[str] | None,
) -> None:
    if transport == "streamable-http":
        await _run_streamable_http_transport(
            host=host,
            port=port,
            root_path=root_path,
            allowed_origins=allowed_origins,
        )
        return

    await _run_sse_http_transport(
        host=host,
        port=port,
        root_path=root_path,
        allowed_origins=allowed_origins,
    )


async def main(argv: Sequence[str] | None = None):
    args = _parse_args(argv)
    transport = (args.transport or os.getenv("MCP_TRANSPORT", "stdio")).lower()

    try:
        if transport in {"http", "streamable-http"}:
            http_options = _resolve_http_options(args)
            await _run_http_transport(
                transport=transport,
                host=http_options["host"],
                port=http_options["port"],
                root_path=http_options["root_path"],
                allowed_origins=http_options["allowed_origins"],
            )
        elif transport == "stdio":
            await _run_stdio_transport()
        else:
            raise ValueError(f"Unsupported transport '{transport}'. Use 'stdio', 'http', or 'streamable-http'.")
    except asyncio.CancelledError:
        logger.info("Shutdown requested, cancelling outstanding tasks.")
