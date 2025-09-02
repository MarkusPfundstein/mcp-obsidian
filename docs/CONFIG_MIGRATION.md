# Configuration System Migration Guide

This guide helps developers understand the new centralized configuration system and how to migrate existing code.

## Overview

As of v0.3.0, mcp-obsidian uses a centralized configuration system based on `pydantic-settings`. This replaces the previous approach of reading environment variables directly in multiple places throughout the codebase.

**New to the configuration system?** Read [CONFIG.md](CONFIG.md) first to understand the architecture and benefits.

## Key Changes

### Before (Scattered Configuration)
```python
# In tools.py
api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")

# In each tool handler
api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
```

### After (Centralized Configuration)
```python
# Configuration loaded once
from .config import Settings

# Passed to components that need it
class ToolHandler:
    def __init__(self, tool_name: str, config: Settings = None):
        self.config = config
    
    def get_obsidian_client(self):
        return obsidian.Obsidian(config=self.config)
```

## For Tool Developers

### Creating a New Tool

When creating a new tool handler, follow this pattern:

```python
from typing import Optional
from mcp.types import Tool, TextContent
from .config import Settings

class YourNewToolHandler(ToolHandler):
    def __init__(self, config: Optional['Settings'] = None):
        super().__init__("your_tool_name", config)
    
    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description="Your tool description",
            inputSchema={...}
        )
    
    def run_tool(self, args: dict):
        # Use the configured Obsidian client
        api = self.get_obsidian_client()
        
        # Your tool logic here
        result = api.some_method()
        
        return [TextContent(type="text", text=result)]
```

Then register it in `server.py`:

```python
# In server.py
add_tool_handler(tools.YourNewToolHandler(config))
```

### Migrating Existing Tools

If you have an existing tool that directly uses environment variables:

1. **Update the `__init__` method** to accept config:
   ```python
   # Before
   def __init__(self):
       super().__init__("tool_name")
   
   # After
   def __init__(self, config: Optional['Settings'] = None):
       super().__init__("tool_name", config)
   ```

2. **Replace Obsidian instantiation**:
   ```python
   # Before
   api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
   
   # After
   api = self.get_obsidian_client()
   ```

3. **Update registration** in server.py:
   ```python
   # Before
   add_tool_handler(tools.YourToolHandler())
   
   # After
   add_tool_handler(tools.YourToolHandler(config))
   ```

## For Core Contributors

### Adding New Configuration Options

To add a new configuration option:

1. **Add to `config.py`**:
   ```python
   class Settings(BaseSettings):
       # Existing fields...
       
       your_new_option: str = Field(
           default="default_value",
           description="Description of the option",
           alias="YOUR_ENV_VAR_NAME"
       )
   ```

2. **Add validation if needed**:
   ```python
   @field_validator("your_new_option")
   @classmethod
   def validate_option(cls, v: str) -> str:
       # Your validation logic
       return v
   ```

3. **Use in your code**:
   ```python
   # Access via config object
   value = self.config.your_new_option
   ```

### Working with the Obsidian Client

The `Obsidian` class supports both configuration styles:

```python
# New way (preferred) - with config object
from .config import get_settings

config = get_settings()
client = Obsidian(config=config)

# Old way (backward compatible) - with individual parameters
client = Obsidian(
    api_key="key",
    host="127.0.0.1",
    port=27124
)

# Config object takes precedence if both are provided
client = Obsidian(
    api_key="ignored",  # This will be ignored
    config=config       # Config values will be used
)
```

## Environment Variables

The following environment variables are supported:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_API_KEY` | Yes | - | API key from Obsidian Local REST API plugin |
| `OBSIDIAN_HOST` | No | `127.0.0.1` | Obsidian REST API host |
| `OBSIDIAN_PORT` | No | `27124` | Obsidian REST API port |
| `OBSIDIAN_PROTOCOL` | No | `https` | Protocol (`http` or `https`) |
| `OBSIDIAN_CONNECT_TIMEOUT` | No | `3` | Connection timeout in seconds (1-60) |
| `OBSIDIAN_READ_TIMEOUT` | No | `6` | Read timeout in seconds (1-300) |
| `OBSIDIAN_VERIFY_SSL` | No | `false` | Verify SSL certificates |

## Testing with Configuration

### Unit Tests

For unit tests, you can create a test configuration:

```python
from mcp_obsidian.config import Settings

def test_your_tool():
    # Create test config
    test_config = Settings(
        obsidian_api_key="test-key",
        obsidian_host="test-host",
        obsidian_port=8080
    )
    
    # Create handler with test config
    handler = YourToolHandler(config=test_config)
    
    # Mock the Obsidian client
    with patch.object(handler, 'get_obsidian_client') as mock_client:
        mock_client.return_value = MagicMock()
        # Your test logic
```

### Integration Tests

For integration tests, use environment variables:

```python
def test_with_env_vars():
    with patch.dict(os.environ, {
        "OBSIDIAN_API_KEY": "test-key",
        "OBSIDIAN_HOST": "localhost",
        "OBSIDIAN_PORT": "8080"
    }):
        config = get_settings()
        handler = YourToolHandler(config=config)
        # Your test logic
```

## Backward Compatibility

The system maintains backward compatibility:

1. **Obsidian client** still accepts individual parameters
2. **Tool handlers** have optional config parameter
3. **Environment variables** are still read as fallback

However, new code should use the centralized configuration approach for consistency.

## Common Issues and Solutions

### Issue: "OBSIDIAN_API_KEY environment variable required"
**Solution**: The error now comes from the config system. Ensure the environment variable is set or pass a config object with the API key.

### Issue: Tool doesn't use new configuration
**Solution**: Ensure the tool handler:
1. Accepts `config` in `__init__`
2. Passes it to `super().__init__()`
3. Uses `self.get_obsidian_client()` instead of creating Obsidian instances directly

### Issue: Tests failing after migration
**Solution**: Mock or set environment variables in tests:
```python
# At the top of test file
os.environ["OBSIDIAN_API_KEY"] = "test-api-key"
```

## Benefits of the New System

1. **Single source of truth** - All configuration in one place
2. **Type safety** - Pydantic validates types and values
3. **Better testing** - Easy to inject test configurations
4. **Future-proof** - Ready for CLI arguments via Typer
5. **Clear defaults** - All defaults defined in one place
6. **Validation** - Port ranges, protocol values, etc. are validated

## Questions or Issues?

If you encounter issues with the configuration system, please:
1. Check this guide first
2. Look at existing tool implementations for examples
3. Open an issue with the `configuration` label