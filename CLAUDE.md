# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides integration between Claude and Obsidian through the Obsidian Local REST API community plugin. It allows Claude to interact with Obsidian vaults by reading, searching, creating, and modifying notes.

## Key Dependencies and Setup

- Python 3.11+ required
- Main dependencies: `mcp`, `python-dotenv`, `requests`
- Uses UV package manager for dependency management
- Requires Obsidian Local REST API plugin installed and configured in Obsidian

## Development Commands

```bash
# Install dependencies and sync lockfile
uv sync

# Run the MCP server locally for development
uv --directory /path/to/mcp-obsidian run mcp-obsidian

# Run with UV from project directory
uv run mcp-obsidian

# Check types with pyright (development dependency)
uv run pyright

# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/mcp_obsidian --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_obsidian.py

# Run tests in verbose mode
uv run pytest -v

# Debug with MCP Inspector
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-obsidian run mcp-obsidian

# Monitor server logs
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-mcp-obsidian.log
```

## Architecture and Code Structure

### Entry Points
- `src/mcp_obsidian/__init__.py`: Package entry point, defines `main()` function
- `src/mcp_obsidian/server.py`: MCP server implementation, handles tool registration and execution

### Core Components

1. **Tool System** (`src/mcp_obsidian/tools.py`):
   - Base `ToolHandler` class for all tool implementations
   - Each tool is a separate handler class inheriting from `ToolHandler`
   - Tools are registered in `server.py` via `add_tool_handler()`
   - Current tools: ListFilesInVault, ListFilesInDir, GetFileContents, Search, PatchContent, AppendContent, PutContent, DeleteFile, ComplexSearch, BatchGetFileContents, PeriodicNotes, RecentPeriodicNotes, RecentChanges

2. **Obsidian API Client** (`src/mcp_obsidian/obsidian.py`):
   - `Obsidian` class wraps the REST API communication
   - Handles authentication via Bearer token
   - Configurable protocol (http/https), host, and port
   - Methods correspond to REST API endpoints
   - Error handling via `_safe_call()` wrapper

3. **MCP Server** (`src/mcp_obsidian/server.py`):
   - Uses MCP's `Server` class
   - Implements `@app.list_tools()` and `@app.call_tool()` handlers
   - Tool handlers stored in global `tool_handlers` dictionary
   - Runs as stdio server for Claude Desktop integration

### Environment Configuration

Required environment variables:
- `OBSIDIAN_API_KEY`: API key from Obsidian Local REST API plugin (required)
- `OBSIDIAN_HOST`: Obsidian host (default: "127.0.0.1")
- `OBSIDIAN_PORT`: Obsidian port (default: "27124")
- `OBSIDIAN_PROTOCOL`: Protocol to use (default: "https")

These can be set via `.env` file or in Claude Desktop's configuration.

### Adding New Tools

To add a new tool:
1. Create a new class in `tools.py` inheriting from `ToolHandler`
2. Implement `get_tool_description()` with MCP Tool schema
3. Implement `run_tool()` to handle the tool execution
4. Register the handler in `server.py` using `add_tool_handler()`

### OpenAPI Integration

The repository includes `openapi.yaml` which documents the Obsidian REST API endpoints. This can be referenced when implementing new tools or understanding the API structure.

## Testing Strategy

### Test Structure
- Tests are located in the `tests/` directory
- Test files follow the pattern `test_*.py`
- Fixtures are defined in `tests/conftest.py`
- Mocking is used to avoid requiring a real Obsidian instance

### Running Tests
Tests use pytest and should be run before any refactoring:
- `uv run pytest` - Run all tests
- `uv run pytest -v` - Verbose output
- `uv run pytest --cov=src/mcp_obsidian` - With coverage

### Test Coverage Areas
1. **Unit Tests**: Individual components (Obsidian client, tool handlers)
2. **Integration Tests**: Tool registration and execution flow
3. **Configuration Tests**: Environment variable handling and validation

### Before Refactoring
Always ensure all tests pass before and after refactoring. The test suite acts as a safety net to catch regressions.