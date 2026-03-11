# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install/sync dependencies
uv sync

# Run the server (requires OBSIDIAN_API_KEY env var)
uv run mcp-obsidian

# Type checking
uv run pyright

# Debug with MCP Inspector
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-obsidian run mcp-obsidian
```

## Required Environment Variables

Set in `.env` or in the MCP server config:

- `OBSIDIAN_API_KEY` — from the Obsidian Local REST API plugin settings (required)
- `OBSIDIAN_HOST` — default `127.0.0.1`
- `OBSIDIAN_PORT` — default `27124`
- `OBSIDIAN_PROTOCOL` — default `https`

## Architecture

```
src/mcp_obsidian/
  __init__.py   — entry point, calls server.main()
  server.py     — MCP Server setup; registers all tool handlers; handles tool dispatch
  obsidian.py   — Obsidian class: thin HTTP client wrapping the Obsidian REST API
  tools.py      — ToolHandler base class + one subclass per MCP tool
```

**Data flow:** MCP client → `server.py` (`call_tool`) → `ToolHandler.run_tool()` in `tools.py` → `Obsidian` methods in `obsidian.py` → Obsidian REST API

**Adding a new tool:**
1. Add a method to `Obsidian` in `obsidian.py` for the API call
2. Create a `ToolHandler` subclass in `tools.py` with `get_tool_description()` and `run_tool()`
3. Register it with `add_tool_handler()` in `server.py`

All MCP tool names use the `obsidian_` prefix (e.g., `obsidian_simple_search`).

The `Obsidian._safe_call()` wrapper normalizes all HTTP and request errors into plain `Exception`s. SSL verification is disabled by default (the plugin uses a self-signed cert).
