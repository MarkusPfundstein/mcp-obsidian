"""Tests for the MCP server."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_obsidian import server
from mcp.types import Tool

class TestServer:
    """Test the MCP server functionality."""
    
    def test_tool_handler_registration(self):
        """Test that tool handlers are registered correctly."""
        # Clear existing handlers for test
        original_handlers = server.tool_handlers.copy()
        server.tool_handlers.clear()
        
        # Create mock handler
        mock_handler = MagicMock()
        mock_handler.name = "test_tool"
        
        # Register handler
        server.add_tool_handler(mock_handler)
        
        # Check registration
        assert "test_tool" in server.tool_handlers
        assert server.get_tool_handler("test_tool") == mock_handler
        assert server.get_tool_handler("nonexistent") is None
        
        # Restore original handlers
        server.tool_handlers = original_handlers
        
    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools."""
        # Create mock handlers
        mock_handler1 = MagicMock()
        mock_handler1.get_tool_description.return_value = Tool(
            name="tool1",
            description="Tool 1 description",
            inputSchema={"type": "object"}
        )
        
        mock_handler2 = MagicMock()
        mock_handler2.get_tool_description.return_value = Tool(
            name="tool2",
            description="Tool 2 description",
            inputSchema={"type": "object"}
        )
        
        # Temporarily replace handlers
        original_handlers = server.tool_handlers.copy()
        server.tool_handlers = {
            "tool1": mock_handler1,
            "tool2": mock_handler2
        }
        
        # Test list_tools
        tools = await server.list_tools()
        
        assert len(tools) == 2
        assert any(t.name == "tool1" for t in tools)
        assert any(t.name == "tool2" for t in tools)
        
        # Restore original handlers
        server.tool_handlers = original_handlers
        
    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Test successful tool call."""
        # Create mock handler
        mock_handler = MagicMock()
        mock_handler.run_tool.return_value = [
            MagicMock(type="text", text="Success")
        ]
        
        # Temporarily replace handlers
        original_handlers = server.tool_handlers.copy()
        server.tool_handlers = {"test_tool": mock_handler}
        
        # Test call_tool
        result = await server.call_tool("test_tool", {"arg1": "value1"})
        
        mock_handler.run_tool.assert_called_once_with({"arg1": "value1"})
        assert len(result) == 1
        assert result[0].text == "Success"
        
        # Restore original handlers
        server.tool_handlers = original_handlers
        
    @pytest.mark.asyncio
    async def test_call_tool_invalid_arguments(self):
        """Test tool call with invalid arguments."""
        with pytest.raises(RuntimeError) as exc_info:
            await server.call_tool("any_tool", "not_a_dict")
        assert "arguments must be dictionary" in str(exc_info.value)
        
    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self):
        """Test calling an unknown tool."""
        with pytest.raises(ValueError) as exc_info:
            await server.call_tool("unknown_tool", {})
        assert "Unknown tool: unknown_tool" in str(exc_info.value)
        
    @pytest.mark.asyncio
    async def test_call_tool_handler_exception(self):
        """Test tool handler raising an exception."""
        # Create mock handler that raises exception
        mock_handler = MagicMock()
        mock_handler.run_tool.side_effect = Exception("Handler error")
        
        # Temporarily replace handlers
        original_handlers = server.tool_handlers.copy()
        server.tool_handlers = {"failing_tool": mock_handler}
        
        # Test call_tool
        with pytest.raises(RuntimeError) as exc_info:
            await server.call_tool("failing_tool", {})
        assert "Handler error" in str(exc_info.value)
        
        # Restore original handlers
        server.tool_handlers = original_handlers
        
    def test_all_tools_registered(self):
        """Test that all expected tools are registered."""
        expected_tools = [
            "obsidian_list_files_in_vault",
            "obsidian_list_files_in_dir",
            "obsidian_get_file_contents",
            "obsidian_search",
            "obsidian_patch_content",
            "obsidian_append_content",
            "obsidian_put_content",
            "obsidian_delete_file",
            "obsidian_complex_search",
            "obsidian_batch_get_file_contents",
            "obsidian_periodic_notes",
            "obsidian_recent_periodic_notes",
            "obsidian_recent_changes"
        ]
        
        for tool_name in expected_tools:
            assert tool_name in server.tool_handlers, f"Tool {tool_name} not registered"