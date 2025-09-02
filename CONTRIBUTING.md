# Contributing to MCP Obsidian

Thank you for your interest in contributing to the MCP Obsidian server! This guide will help you get started with development and ensure your contributions align with the project's standards.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/mcp-obsidian.git
   cd mcp-obsidian
   ```

2. **Install dependencies**
   ```bash
   uv sync --all-groups
   ```

3. **Set up environment variables**
   Create a `.env` file with your Obsidian API credentials:
   ```
   OBSIDIAN_API_KEY=your_api_key
   OBSIDIAN_HOST=127.0.0.1
   OBSIDIAN_PORT=27124
   OBSIDIAN_PROTOCOL=https
   ```

## Running Tests

We maintain a test suite to ensure code quality and prevent regressions. **Always run tests before submitting a PR.**

### Important: Test Environment
**Tests require a clean environment.** If you have a `.env` file for local development, you must remove or rename it before running tests. The test suite will fail with a clear error message if a `.env` file is detected.

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_obsidian.py

# Run with coverage report
uv run pytest --cov=src/mcp_obsidian --cov-report=term-missing
```

### Test Structure
- `tests/conftest.py` - Shared fixtures and test configuration
- `tests/test_basic_integration.py` - Core functionality tests (run these as smoke tests)
- `tests/test_obsidian.py` - Obsidian API client tests
- `tests/test_server.py` - MCP server tests
- `tests/test_tools.py` - Individual tool handler tests

## Code Style

1. **Type hints**: Use type hints for all function parameters and return values
2. **Error handling**: Use the `_safe_call` pattern for API calls
3. **Tool handlers**: Inherit from `ToolHandler` base class
4. **Environment variables**: Currently read directly, but will be refactored to use centralized configuration

## Adding New Tools

To add a new tool:

1. **Create the tool handler** in `src/mcp_obsidian/tools.py`:
   ```python
   class YourToolHandler(ToolHandler):
       def __init__(self):
           super().__init__("obsidian_your_tool")
       
       def get_tool_description(self):
           return Tool(
               name=self.name,
               description="Tool description",
               inputSchema={...}
           )
       
       def run_tool(self, args: dict):
           # Implementation
   ```

2. **Register the handler** in `src/mcp_obsidian/server.py`:
   ```python
   add_tool_handler(tools.YourToolHandler())
   ```

3. **Add tests** in `tests/test_tools.py`:
   ```python
   class TestYourToolHandler:
       def test_tool_description(self):
           # Test the tool metadata
       
       def test_run_tool(self):
           # Test the tool execution
   ```

4. **Update documentation** if needed

## Testing Guidelines

- **Mock external dependencies**: Use `unittest.mock` to mock Obsidian API calls
- **Test both success and failure cases**: Include tests for error handling
- **Use fixtures**: Leverage pytest fixtures in `conftest.py` for common test data
- **Isolate tests**: Each test should be independent and not rely on others

## Debugging

For debugging MCP server interactions:

```bash
# Use MCP Inspector
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-obsidian run mcp-obsidian

# Monitor server logs
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-mcp-obsidian.log
```

## Pull Request Process

1. **Create a feature branch**: `git checkout -b feature/your-feature`
2. **Write tests** for your changes
3. **Run the test suite**: `uv run pytest`
4. **Check types**: `uv run pyright` (if applicable)
5. **Update documentation** if needed
6. **Create a pull request** with a clear description

### PR Checklist
- [ ] Tests pass locally
- [ ] New code has tests
- [ ] Documentation updated (if needed)
- [ ] No hardcoded credentials or sensitive data
- [ ] Tool handlers follow existing patterns

## Upcoming Refactoring

We're planning to refactor the configuration system to use Pydantic Settings. If you're working on configuration-related code, please coordinate to avoid conflicts. See `TODO.md` for details.

## Questions?

If you have questions about contributing, please open an issue for discussion.