from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from mcp.server import Server
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .config import Settings
from .index import DocumentationIndex, DocumentationSource
from .serialization import serialize_json
from .source import ObsidianSource
from .tools import ToolService, tool_definitions


logger = logging.getLogger("documentation-mcp")
app = Server("documentation-mcp")
_service: ToolService | None = None


def configure(settings: Settings, source: DocumentationSource | None = None) -> ToolService:
    global _service
    documentation_source = source or ObsidianSource(settings)
    index = DocumentationIndex(settings)
    service = ToolService(index, documentation_source)
    _service = service
    return _service


def get_service() -> ToolService:
    if _service is None:
        raise RuntimeError("documentation-mcp has not been configured")
    return _service


@app.list_tools()
async def list_tools() -> list[Tool]:
    return tool_definitions()


@app.call_tool()
async def call_tool(
    name: str,
    arguments: Any,
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    if not isinstance(arguments, dict):
        raise RuntimeError("arguments must be an object")

    started = perf_counter()
    try:
        service = get_service()
        if name == "refresh_index":
            result = await asyncio.to_thread(service.dispatch, name, arguments)
        else:
            result = service.dispatch(name, arguments)
        text = serialize_json(result)
    except Exception as exc:
        logger.warning("tool=%s status=error error_type=%s", name, exc.__class__.__name__)
        raise RuntimeError(f"{name} failed: {exc}") from exc

    elapsed_ms = (perf_counter() - started) * 1000
    result_count = len(result.get("results", [])) if isinstance(result, dict) else 0
    logger.info(
        "tool=%s status=ok latency_ms=%.3f result_count=%d response_characters=%d",
        name,
        elapsed_ms,
        result_count,
        len(text),
    )
    return [TextContent(type="text", text=text)]


async def run() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        service = get_service()
        initial_refresh = (
            asyncio.create_task(asyncio.to_thread(service.refresh_index))
            if service.begin_initial_refresh()
            else None
        )
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
        finally:
            if initial_refresh is not None:
                await initial_refresh
