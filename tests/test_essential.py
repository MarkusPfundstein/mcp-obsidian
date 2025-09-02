"""Essential tests that must pass before any refactoring.
These tests verify the core functionality works as expected.
"""
import pytest
import json
import os
from unittest.mock import MagicMock, patch

# Set environment variables before importing modules that depend on them
os.environ["OBSIDIAN_API_KEY"] = "test-api-key"

from mcp_obsidian.obsidian import Obsidian
from mcp_obsidian import server
from mcp_obsidian.tools import (
    ListFilesInVaultToolHandler,
    ListFilesInDirToolHandler,
    GetFileContentsToolHandler,
)

class TestEssentialFunctionality:
    """Tests for essential functionality that must not break."""
    
    def test_obsidian_client_initialization(self):
        """Test that Obsidian client can be initialized with custom values."""
        client = Obsidian(
            api_key="test-key",
            protocol="https",
            host="127.0.0.1",
            port=27124
        )
        assert client.api_key == "test-key"
        assert client.protocol == "https"
        assert client.host == "127.0.0.1"
        assert client.port == 27124
        assert client.get_base_url() == "https://127.0.0.1:27124"
    
    def test_critical_tools_registered(self):
        """Test that critical tools are registered in the server."""
        critical_tools = [
            "obsidian_list_files_in_vault",
            "obsidian_list_files_in_dir",
            "obsidian_get_file_contents",
            "obsidian_append_content",
            "obsidian_delete_file",
        ]
        
        for tool_name in critical_tools:
            assert tool_name in server.tool_handlers, f"Critical tool {tool_name} not registered"
    
    @pytest.mark.asyncio
    async def test_server_can_list_tools(self):
        """Test that server can list available tools."""
        tools = await server.list_tools()
        assert len(tools) > 0
        
        # Verify tools have required structure
        for tool in tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
            assert tool.name in server.tool_handlers
    
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_list_files_tool_execution(self, mock_obsidian_class):
        """Test that list files tool works correctly."""
        # Setup mock
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.list_files_in_vault.return_value = [
            {"path": "note1.md", "type": "file"},
            {"path": "folder1", "type": "directory"}
        ]
        
        # Execute tool
        handler = ListFilesInVaultToolHandler()
        result = handler.run_tool({})
        
        # Verify
        assert len(result) == 1
        assert result[0].type == "text"
        # Result should be JSON
        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["path"] == "note1.md"
    
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_get_file_contents_tool(self, mock_obsidian_class):
        """Test that get file contents tool works correctly."""
        # Setup mock
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.get_file_contents.return_value = "# Test Note\nContent here"
        
        # Execute tool
        handler = GetFileContentsToolHandler()
        result = handler.run_tool({"filepath": "test.md"})
        
        # Verify
        assert len(result) == 1
        assert result[0].type == "text"
        # The actual implementation returns JSON wrapped content
        # We need to check what format is actually returned
        text = result[0].text
        assert "Test Note" in text or "Test Note" in json.loads(text)
    
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_list_files_in_dir_tool(self, mock_obsidian_class):
        """Test that list files in directory tool works correctly."""
        # Setup mock
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.list_files_in_dir.return_value = [
            {"path": "folder/note2.md", "type": "file"}
        ]
        
        # Execute tool
        handler = ListFilesInDirToolHandler()
        result = handler.run_tool({"dirpath": "folder"})
        
        # Verify
        mock_client.list_files_in_dir.assert_called_once_with("folder")
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data[0]["path"] == "folder/note2.md"
    
    def test_tool_error_handling(self):
        """Test that tools handle missing arguments correctly."""
        handler = ListFilesInDirToolHandler()
        
        # Should raise error for missing required argument
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({})
        
        assert "dirpath" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_server_handles_invalid_tool(self):
        """Test that server properly handles calls to non-existent tools."""
        with pytest.raises(ValueError) as exc_info:
            await server.call_tool("non_existent_tool", {})
        
        assert "Unknown tool" in str(exc_info.value)